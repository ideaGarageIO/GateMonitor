"""MQTT client for communicating with the LoRa gateway.

This module provides the MQTTClient class which handles all communication
with the Mosquitto MQTT broker. It subscribes to gate status topics and
publishes commands to control the gate.
"""

import json
import logging
from datetime import datetime
from typing import Any, Callable, Optional

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

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="gate_monitor_server",
        )

        if username and password:
            self.client.username_pw_set(username, password)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.status = GateStatus()
        self.history: list[HistoryEntry] = []
        self.max_history = 100
        self._status_callbacks: list[Callable[[GateStatus], None]] = []
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected to the MQTT broker.

        Returns:
            True if connected to the broker, False otherwise.
        """
        return self._connected

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

    def connect(self) -> None:
        """Connect to the MQTT broker.

        Establishes a connection to the broker and starts the network
        loop in a background thread.

        Raises:
            ConnectionRefusedError: If the broker refuses the connection.
            OSError: If the broker is unreachable.
        """
        logger.info("Connecting to MQTT broker at %s:%d", self.host, self.port)
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def disconnect(self) -> None:
        """Disconnect from the MQTT broker.

        Stops the network loop and cleanly disconnects from the broker.
        """
        self.client.loop_stop()
        self.client.disconnect()
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
        else:
            logger.error("MQTT connection failed with code %d", rc)
            self._connected = False

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        rc: int,
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
        logger.warning("Disconnected from MQTT broker (rc=%d)", rc)

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
            elif topic == self.TOPIC_RSSI:
                self.status.rssi = int(payload)
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

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of a status update.

        Catches and logs any exceptions raised by callbacks to prevent
        one failing callback from affecting others.
        """
        for callback in self._status_callbacks:
            try:
                callback(self.status)
            except Exception as e:
                logger.error("Error in status callback: %s", e)
