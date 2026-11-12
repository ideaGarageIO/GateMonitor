"""MQTT client for communicating with the LoRa gateway.

This module provides the MQTTClient class which handles all communication
with the Mosquitto MQTT broker. It subscribes to gate status topics and
publishes commands to control the gate.
"""

import json
import logging
import os
import socket
from datetime import datetime
from typing import Any, Callable, Optional

TopicHandler = Callable[[str, str], None]
ConnectHandler = Callable[[], None]

import paho.mqtt.client as mqtt

from .models import Command, GateState, GateStatus, HistoryEntry

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT client for gate monitor communication.

    This class manages the connection to the MQTT broker and handles
    all message processing for gate status updates and command publishing.

    Attributes:
        TOPIC_STATUS: Topic for JSON status messages from gateway.
        TOPIC_COMMAND: Topic for sending commands to gateway.
        TOPIC_BATTERY: Topic for battery voltage updates.
        TOPIC_RSSI: Topic for signal strength updates.
        TOPIC_ONLINE: Topic for online/offline status.
        TOPIC_GATEWAY_HEARTBEAT: Topic for gateway heartbeat messages.
        GATEWAY_TIMEOUT_MS: Time in ms before gateway is considered offline.

    Example:
        >>> client = MQTTClient(host="192.168.1.100")
        >>> client.add_status_callback(my_callback)
        >>> client.connect()
        >>> client.send_command(Command.OPEN)
    """

    TOPIC_STATUS = "gate/status"
    TOPIC_COMMAND = "gate/command"
    TOPIC_BATTERY = "gate/battery"
    TOPIC_RSSI = "gate/rssi"
    TOPIC_ONLINE = "gate/online"
    TOPIC_GATEWAY_HEARTBEAT = "gateway/heartbeat"
    TOPIC_SERVER_STATUS = "gatemonitor/status"  # retained online/offline (LWT)
    EXTRA_SUBSCRIPTIONS = ("coop/#", "solar/#", "homeassistant/status")
    GATEWAY_TIMEOUT_MS = 2000  # 2 seconds (4 missed heartbeats at 2Hz)

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        """Initialize the MQTT client.

        Args:
            host: MQTT broker hostname or IP address.
            port: MQTT broker port (default 1883).
            username: Optional username for authentication.
            password: Optional password for authentication.
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password

        # Unique per process: brokers disconnect an existing session when a
        # second client connects with the same id (e.g. dev box + Pi).
        client_id = os.getenv("MQTT_CLIENT_ID") or f"gate_monitor_{socket.gethostname()}_{os.getpid()}"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id[:64])

        if username and password:
            self.client.username_pw_set(username, password)
        # Broker marks the server offline if we drop without saying goodbye.
        self.client.will_set(self.TOPIC_SERVER_STATUS, "offline", qos=1, retain=True)
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.status = GateStatus()
        self.history: list[HistoryEntry] = []
        self.max_history = 100
        self._status_callbacks: list[Callable[[GateStatus], None]] = []
        self._connected = False
        self._topic_handlers: list[tuple[str, TopicHandler]] = []
        self._connect_handlers: list[ConnectHandler] = []
        self.last_command: Optional[Command] = None

        # Gateway heartbeat tracking
        self._last_gateway_heartbeat: Optional[datetime] = None
        self._gateway_online = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to the MQTT broker.

        Returns:
            True if connected to the broker, False otherwise.
        """
        return self._connected

    @property
    def is_gateway_online(self) -> bool:
        """Check if the gateway is online (receiving heartbeats).

        Returns:
            True if gateway heartbeat received within timeout period.
        """
        return self._gateway_online

    def check_gateway_timeout(self) -> bool:
        """Check if gateway has timed out and update status accordingly.

        This should be called periodically to detect gateway disconnection.

        Returns:
            True if gateway status changed (went offline), False otherwise.
        """
        if self._last_gateway_heartbeat is None:
            # No heartbeat ever received
            if self._gateway_online:
                logger.warning("Gateway timeout - never received heartbeat but was marked online")
                self._gateway_online = False
                self.status.state = GateState.UNKNOWN
                self.status.online = False
                self.status.last_update = datetime.now()
                self._notify_callbacks()
                return True
            return False

        elapsed = (datetime.now() - self._last_gateway_heartbeat).total_seconds() * 1000

        if elapsed > self.GATEWAY_TIMEOUT_MS:
            if self._gateway_online:
                logger.warning("Gateway timeout - no heartbeat for %.1f seconds", elapsed / 1000)
                self._gateway_online = False
                # Set gate status to unknown/offline when gateway disconnects
                self.status.state = GateState.UNKNOWN
                self.status.online = False
                self.status.last_update = datetime.now()
                logger.info("Setting gate state to UNKNOWN, online=False, notifying callbacks")
                self._notify_callbacks()
                return True
        return False

    def add_status_callback(self, callback: Callable[[GateStatus], None]) -> None:
        """Register a callback function for status updates.

        The callback will be invoked whenever a new status update is
        received from the gateway.

        Args:
            callback: A function that takes a GateStatus object as its
                only argument.
        """
        self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[GateStatus], None]) -> None:
        """Remove a previously registered status callback.

        Args:
            callback: The callback function to remove.
        """
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def add_topic_handler(self, prefix: str, handler: TopicHandler) -> None:
        """Route messages whose topic starts with ``prefix`` to ``handler(topic, payload)``.

        Handlers run on the paho network thread; hop to asyncio before touching
        async state.
        """
        self._topic_handlers.append((prefix, handler))

    def add_connect_handler(self, handler: ConnectHandler) -> None:
        """Call ``handler()`` (on the network thread) after every successful (re)connect."""
        self._connect_handlers.append(handler)

    def publish(self, topic: str, payload: str, retain: bool = False, qos: int = 0) -> bool:
        """Publish a message. Returns False (and drops it) when not connected."""
        if not self._connected:
            return False
        self.client.publish(topic, payload, qos=qos, retain=retain)
        return True

    def connect(self) -> None:
        """Start connecting to the MQTT broker in the background.

        Uses paho's async connect so the server starts even when the broker
        is down, and keeps retrying (1s -> 30s backoff) until it comes up.
        """
        logger.info("Connecting to MQTT broker at %s:%d", self.host, self.port)
        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker.

        Publishes the offline status, then stops the network loop.
        """
        if self._connected:
            self.client.publish(self.TOPIC_SERVER_STATUS, "offline", qos=1, retain=True)
        self.client.disconnect()
        self.client.loop_stop()
        logger.info("Disconnected from MQTT broker")

    def send_command(self, command: Command) -> None:
        """Send a command to the gate via MQTT.

        The command is published to the gate/command topic where the
        gateway will receive it and forward to the gate node via LoRa.

        Args:
            command: The command to send (OPEN, CLOSE, STOP, or STATUS).
        """
        cmd_str = command.name
        logger.info("Sending command: %s", cmd_str)
        self.client.publish(self.TOPIC_COMMAND, cmd_str)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: int,
        properties: Any = None,
    ) -> None:
        """Handle MQTT connection events.

        Args:
            client: The MQTT client instance.
            userdata: User data (unused).
            flags: Connection flags.
            rc: Connection result code (0 = success).
            properties: MQTT v5 properties (optional).
        """
        if rc == 0:
            logger.info("Connected to MQTT broker")
            self._connected = True
            client.subscribe("gate/#")
            client.subscribe("gateway/#")
            for topic in self.EXTRA_SUBSCRIPTIONS:
                client.subscribe(topic)
            logger.info("Subscribed to gate/#, gateway/#, %s", ", ".join(self.EXTRA_SUBSCRIPTIONS))
            client.publish(self.TOPIC_SERVER_STATUS, "online", qos=1, retain=True)
            for handler in self._connect_handlers:
                try:
                    handler()
                except Exception:  # noqa: BLE001
                    logger.exception("MQTT connect handler failed")
        else:
            logger.error("MQTT connection failed with code %d", rc)
            self._connected = False

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        rc: Any,
        properties: Any = None,
    ) -> None:
        """Handle MQTT disconnection events.

        Args:
            client: The MQTT client instance.
            userdata: User data (unused).
            rc: Disconnection reason code.
            properties: MQTT v5 properties (optional).
        """
        self._connected = False
        logger.warning("Disconnected from MQTT broker (rc=%s)", rc)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        """Handle incoming MQTT messages.

        Routes messages to appropriate handlers based on topic.

        Args:
            client: The MQTT client instance.
            userdata: User data (unused).
            msg: The received MQTT message.
        """
        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        logger.debug("MQTT message: %s = %s", topic, payload)

        try:
            if topic == self.TOPIC_STATUS:
                self._handle_status(payload)
            elif topic == self.TOPIC_ONLINE:
                self._handle_online(payload)
            elif topic == self.TOPIC_BATTERY:
                self.status.battery_mv = int(payload)
                self.status.last_update = datetime.now()
                self._notify_callbacks()
            elif topic == self.TOPIC_RSSI:
                self.status.rssi = int(payload)
                self.status.last_update = datetime.now()
                self._notify_callbacks()
            elif topic == self.TOPIC_GATEWAY_HEARTBEAT:
                self._handle_gateway_heartbeat(payload)
            elif topic == self.TOPIC_COMMAND:
                # Seen from any source (web UI, Home Assistant, CLI); used to
                # tell "opening" from "closing" while the gate is MOVING.
                self.last_command = Command.from_string(payload)
                self._notify_callbacks()
            else:
                for prefix, handler in self._topic_handlers:
                    if topic.startswith(prefix):
                        handler(topic, payload)
        except ValueError as e:
            logger.error("Error parsing MQTT message value: %s", e)
        except Exception as e:
            logger.error("Error processing MQTT message: %s", e)

    def _handle_status(self, payload: str) -> None:
        """Handle a JSON status message from the gateway.

        Parses the JSON payload, updates the current status, adds an
        entry to the history, and notifies all registered callbacks.

        Args:
            payload: JSON string containing gate status data.

        Raises:
            json.JSONDecodeError: If the payload is not valid JSON.
        """
        try:
            data = json.loads(payload)

            state_map = {
                "UNKNOWN": GateState.UNKNOWN,
                "CLOSED": GateState.CLOSED,
                "OPEN": GateState.OPEN,
                "MOVING": GateState.MOVING,
                "ERROR": GateState.ERROR,
            }

            state_str = data.get("state", "UNKNOWN")
            self.status.state = state_map.get(state_str, GateState.UNKNOWN)
            self.status.battery_mv = data.get("battery", 0)
            self.status.rssi = data.get("rssi", 0)
            self.status.snr = data.get("snr", 0)
            self.status.online = data.get("online", False)
            self.status.last_update = datetime.now()

            entry = HistoryEntry(
                timestamp=self.status.last_update,
                state=self.status.state,
                battery_mv=self.status.battery_mv,
                rssi=self.status.rssi,
                snr=self.status.snr,
            )
            self.history.append(entry)
            if len(self.history) > self.max_history:
                self.history.pop(0)

            self._notify_callbacks()

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in status message: %s", e)

    def _handle_online(self, payload: str) -> None:
        """Handle an online/offline status message.

        Args:
            payload: String containing "online" or "offline".
        """
        self.status.online = payload.lower() == "online"
        self.status.last_update = datetime.now()
        self._notify_callbacks()

    def _handle_gateway_heartbeat(self, payload: str) -> None:
        """Handle a gateway heartbeat message.

        Updates the last heartbeat timestamp and gateway online status.

        Args:
            payload: JSON string containing gateway status data.
        """
        try:
            data = json.loads(payload)
            self._last_gateway_heartbeat = datetime.now()

            # If gateway was offline, mark it as online and notify
            if not self._gateway_online:
                logger.info("Gateway came online - received first heartbeat")
                self._gateway_online = True
                # Notify callbacks to update UI with gateway online status
                self._notify_callbacks()

            # Log every 10th heartbeat or so to avoid spam (roughly every 5 seconds)
            if hasattr(self, '_heartbeat_count'):
                self._heartbeat_count += 1
            else:
                self._heartbeat_count = 1

            if self._heartbeat_count % 10 == 1:
                logger.debug("Gateway heartbeat #%d: gate_online=%s, uptime=%s",
                            self._heartbeat_count, data.get("gate_online"), data.get("uptime"))

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in gateway heartbeat: %s", e)

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of a status update.

        Catches and logs any exceptions raised by callbacks to prevent
        one failing callback from affecting others.
        """
        logger.info("Notifying %d callbacks of status update: state=%s",
                    len(self._status_callbacks), self.status.state)
        for callback in self._status_callbacks:
            try:
                callback(self.status)
            except Exception as e:
                logger.error("Error in status callback: %s", e)
