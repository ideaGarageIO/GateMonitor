"""MQTT client for communicating with the gateway."""

import json
import logging
from datetime import datetime
from typing import Callable, Optional

import paho.mqtt.client as mqtt

from .models import Command, GateState, GateStatus, HistoryEntry

logger = logging.getLogger(__name__)


class MQTTClient:
    """MQTT client for gate monitor."""

    # Topics
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
    ):
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

        # Current status
        self.status = GateStatus()

        # History (last 100 entries)
        self.history: list[HistoryEntry] = []
        self.max_history = 100

        # Callbacks for real-time updates
        self._status_callbacks: list[Callable[[GateStatus], None]] = []

    def add_status_callback(self, callback: Callable[[GateStatus], None]) -> None:
        """Register a callback for status updates."""
        self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[GateStatus], None]) -> None:
        """Remove a status callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)

    def connect(self) -> None:
        """Connect to MQTT broker."""
        logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}")
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from MQTT broker")

    def send_command(self, command: Command) -> None:
        """Send a command to the gate."""
        cmd_str = command.name
        logger.info(f"Sending command: {cmd_str}")
        self.client.publish(self.TOPIC_COMMAND, cmd_str)

    def _on_connect(
        self, client: mqtt.Client, userdata, flags, rc, properties=None
    ) -> None:
        if rc == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to all gate topics
            client.subscribe("gate/#")
        else:
            logger.error(f"MQTT connection failed with code {rc}")

    def _on_disconnect(self, client: mqtt.Client, userdata, rc, properties=None) -> None:
        logger.warning(f"Disconnected from MQTT broker (rc={rc})")

    def _on_message(
        self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage
    ) -> None:
        topic = msg.topic
        payload = msg.payload.decode("utf-8")

        logger.debug(f"MQTT message: {topic} = {payload}")

        try:
            if topic == self.TOPIC_STATUS:
                self._handle_status(payload)
            elif topic == self.TOPIC_ONLINE:
                self._handle_online(payload)
            elif topic == self.TOPIC_BATTERY:
                self.status.battery_mv = int(payload)
            elif topic == self.TOPIC_RSSI:
                self.status.rssi = int(payload)
        except Exception as e:
            logger.error(f"Error processing MQTT message: {e}")

    def _handle_status(self, payload: str) -> None:
        """Handle status JSON message."""
        try:
            data = json.loads(payload)

            # Map state string to enum
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

            # Add to history
            entry = HistoryEntry(
                timestamp=self.status.last_update,
                state=self.status.state,
                battery_mv=self.status.battery_mv,
            )
            self.history.append(entry)
            if len(self.history) > self.max_history:
                self.history.pop(0)

            # Notify callbacks
            for callback in self._status_callbacks:
                try:
                    callback(self.status)
                except Exception as e:
                    logger.error(f"Error in status callback: {e}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in status message: {e}")

    def _handle_online(self, payload: str) -> None:
        """Handle online/offline message."""
        self.status.online = payload.lower() == "online"
        self.status.last_update = datetime.now()

        for callback in self._status_callbacks:
            try:
                callback(self.status)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")
