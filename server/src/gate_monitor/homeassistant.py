"""Home Assistant MQTT discovery.

Publishes retained discovery configs so Home Assistant (connected to the same
Mosquitto broker) automatically creates entities for the gate, each coop and
each solar controller — usable from the HA companion app on a phone.

Entities read the devices' own MQTT topics and send commands straight to
them, so gate control from HA keeps working even if this server is down.
The server-derived topics are ``gatemonitor/gate/cover`` (adds
"opening"/"closing" direction to the gateway's bare ``MOVING`` state using the
last command seen on ``gate/command``) and ``gatemonitor/gateway/online``
(gateway heartbeat timeout). While the server is down those hold their last
retained value.

Discovery is republished whenever HA announces itself on ``homeassistant/status``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from . import __version__
from .devices import CoopStatus, Device, SolarStatus
from .models import Command, GateState, GateStatus

logger = logging.getLogger(__name__)

TOPIC_GATE_COVER = "gatemonitor/gate/cover"
TOPIC_GATEWAY_ONLINE = "gatemonitor/gateway/online"
SERVER_STATUS = "gatemonitor/status"

ORIGIN = {"name": "gate-monitor", "sw_version": __version__}

_DOOR_TO_COVER = (
    "{% set m = {'OPEN':'open','CLOSED':'closed','OPENING':'opening','CLOSING':'closing'} %}"
    "{{ m.get(value_json.door, 'None') }}"
)
_ONLINE_FROM_JSON = "{{ 'online' if value_json.online else 'offline' }}"


def gate_cover_state(status: GateStatus, last_command: Optional[Command]) -> str:
    """Map gateway state to an HA cover state payload."""
    if not status.online:
        return "None"
    if status.state == GateState.OPEN:
        return "open"
    if status.state == GateState.CLOSED:
        return "closed"
    if status.state == GateState.MOVING:
        if last_command == Command.CLOSE:
            return "closing"
        if last_command == Command.STOP:
            return "stopped"
        return "opening"
    return "None"  # UNKNOWN / ERROR -> unknown in HA


class HomeAssistantDiscovery:
    """Builds and publishes discovery payloads through an MQTT ``publish`` callable."""

    def __init__(self, publish, prefix: str = "homeassistant", base_url: Optional[str] = None) -> None:
        # publish(topic, payload, retain) -> bool
        self._publish = publish
        self.prefix = prefix.rstrip("/")
        self.base_url = base_url
        self._announced: set[str] = set()
        self._last_cover: Optional[str] = None
        self._last_gateway: Optional[bool] = None

    # ------------------------------------------------------------------ public

    def announce_all(self, devices: list[Device]) -> None:
        """(Re)publish every discovery config. Call on connect and on HA birth."""
        self._announced.clear()
        self._last_cover = None
        self._last_gateway = None
        for topic, payload in self.gate_configs():
            self._send(topic, payload)
        for device in devices:
            self.announce_device(device)
        logger.info("Published Home Assistant discovery for gate + %d devices", len(devices))

    def announce_device(self, device: Device) -> None:
        """Publish discovery for a device the first time it's seen."""
        if device.id in self._announced:
            return
        configs = self.coop_configs(device) if isinstance(device, CoopStatus) else self.solar_configs(device)
        for topic, payload in configs:
            self._send(topic, payload)
        self._announced.add(device.id)

    def publish_gate_state(self, status: GateStatus, last_command: Optional[Command], gateway_online: bool) -> None:
        """Publish server-derived gate topics (only when they change)."""
        cover = gate_cover_state(status, last_command)
        if cover != self._last_cover and self._publish(TOPIC_GATE_COVER, cover, True):
            self._last_cover = cover
        if gateway_online != self._last_gateway and self._publish(
            TOPIC_GATEWAY_ONLINE, "online" if gateway_online else "offline", True
        ):
            self._last_gateway = gateway_online

    # --------------------------------------------------------------- builders

    def _device(self, ident: str, name: str, model: str) -> dict[str, Any]:
        dev: dict[str, Any] = {
            "identifiers": [f"gatemonitor_{ident}"],
            "name": name,
            "manufacturer": "Gate Monitor (DIY)",
            "model": model,
            "sw_version": __version__,
        }
        if self.base_url:
            dev["configuration_url"] = self.base_url
        return dev

    def _cfg(self, component: str, uid: str, entity_id: str, body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        payload = {
            "unique_id": f"gatemonitor_{uid}",
            "default_entity_id": f"{component}.{entity_id}",
            "object_id": entity_id,  # pre-2025.10 HA uses this for the entity_id
            "origin": ORIGIN,
            **body,
        }
        return f"{self.prefix}/{component}/gatemonitor/{uid}/config", payload

    def gate_configs(self) -> list[tuple[str, dict[str, Any]]]:
        dev = self._device("gate", "Farm Gate", "LoRa gate node + house gateway")
        avail = {
            "availability": [{"topic": "gate/online"}, {"topic": TOPIC_GATEWAY_ONLINE}],
            "availability_mode": "all",
        }
        status_sensor = {"state_topic": "gate/status", "device": dev, **avail}
        return [
            self._cfg("cover", "gate", "farm_gate", {
                "name": None,  # entity takes the device name: "Farm Gate"
                "device_class": "gate",
                "command_topic": "gate/command",
                "payload_open": "OPEN",
                "payload_close": "CLOSE",
                "payload_stop": "STOP",
                "state_topic": TOPIC_GATE_COVER,
                "optimistic": False,
                "device": dev,
                **avail,
            }),
            self._cfg("sensor", "gate_state", "farm_gate_state", {
                "name": "State",
                "icon": "mdi:gate",
                "device_class": "enum",
                "options": [s.name for s in GateState],
                "value_template": "{{ value_json.state }}",
                **status_sensor,
            }),
            self._cfg("sensor", "gate_battery_v", "farm_gate_battery_voltage", {
                "name": "Battery voltage",
                "device_class": "voltage",
                "unit_of_measurement": "V",
                "state_class": "measurement",
                "suggested_display_precision": 2,
                "value_template": "{{ (value_json.battery | float(0)) / 1000 }}",
                **status_sensor,
            }),
            self._cfg("sensor", "gate_battery_pct", "farm_gate_battery", {
                "name": "Battery",
                "device_class": "battery",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                # 12V lead-acid: 11.0V = 0%, 12.6V = 100% (matches the web UI)
                "value_template": (
                    "{% set p = ((value_json.battery | float(0)) - 11000) / 1600 * 100 %}"
                    "{{ ([0, [100, p] | min] | max) | round(0) }}"
                ),
                **status_sensor,
            }),
            self._cfg("sensor", "gate_rssi", "farm_gate_rssi", {
                "name": "Signal strength",
                "device_class": "signal_strength",
                "unit_of_measurement": "dBm",
                "state_class": "measurement",
                "entity_category": "diagnostic",
                "value_template": "{{ value_json.rssi }}",
                **status_sensor,
            }),
            self._cfg("sensor", "gate_snr", "farm_gate_snr", {
                "name": "SNR",
                "icon": "mdi:signal-variant",
                "unit_of_measurement": "dB",
                "state_class": "measurement",
                "entity_category": "diagnostic",
                "value_template": "{{ value_json.snr }}",
                **status_sensor,
            }),
            self._cfg("binary_sensor", "gate_link", "farm_gate_link", {
                "name": "LoRa link",
                "device_class": "connectivity",
                "entity_category": "diagnostic",
                "state_topic": "gate/online",
                "payload_on": "online",
                "payload_off": "offline",
                "device": dev,
            }),
            self._cfg("binary_sensor", "gateway_online", "farm_gate_gateway", {
                "name": "House gateway",
                "device_class": "connectivity",
                "entity_category": "diagnostic",
                "state_topic": TOPIC_GATEWAY_ONLINE,
                "payload_on": "online",
                "payload_off": "offline",
                "availability_topic": SERVER_STATUS,
                "device": dev,
            }),
            self._cfg("button", "gate_refresh", "farm_gate_refresh", {
                "name": "Request status",
                "icon": "mdi:refresh",
                "entity_category": "diagnostic",
                "command_topic": "gate/command",
                "payload_press": "STATUS",
                "device": dev,
                **avail,
            }),
        ]

    def coop_configs(self, coop: CoopStatus) -> list[tuple[str, dict[str, Any]]]:
        cid = coop.id.replace("-", "_")
        state_t = f"coop/{coop.id}/state"
        cmd_t = f"coop/{coop.id}/command"
        dev = self._device(f"coop_{cid}", coop.name, "Coop door controller" + (" (simulated)" if coop.simulated else ""))
        common = {
            "state_topic": state_t,
            "availability_topic": state_t,
            "availability_template": _ONLINE_FROM_JSON,
            "device": dev,
        }
        return [
            self._cfg("cover", f"coop_{cid}_door", f"{cid}_door", {
                "name": "Door",
                "device_class": "door",
                "command_topic": cmd_t,
                "payload_open": "OPEN",
                "payload_close": "CLOSE",
                "payload_stop": "STOP",
                "value_template": _DOOR_TO_COVER,
                **common,
            }),
            self._cfg("binary_sensor", f"coop_{cid}_jammed", f"{cid}_door_jammed", {
                "name": "Door jammed",
                "device_class": "problem",
                "value_template": "{{ 'ON' if value_json.door == 'JAMMED' else 'OFF' }}",
                **common,
            }),
            self._cfg("switch", f"coop_{cid}_auto", f"{cid}_auto_schedule", {
                "name": "Auto schedule",
                "icon": "mdi:weather-sunset",
                "command_topic": cmd_t,
                "payload_on": "AUTO",
                "payload_off": "MANUAL",
                "value_template": "{{ 'AUTO' if value_json.mode == 'auto' else 'MANUAL' }}",
                "state_on": "AUTO",
                "state_off": "MANUAL",
                **common,
            }),
            self._cfg("sensor", f"coop_{cid}_temp", f"{cid}_temperature", {
                "name": "Temperature",
                "device_class": "temperature",
                "unit_of_measurement": "°C",
                "state_class": "measurement",
                "value_template": "{{ value_json.temperature_c }}",
                **common,
            }),
            self._cfg("sensor", f"coop_{cid}_humidity", f"{cid}_humidity", {
                "name": "Humidity",
                "device_class": "humidity",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "value_template": "{{ value_json.humidity }}",
                **common,
            }),
            self._cfg("sensor", f"coop_{cid}_battery_v", f"{cid}_battery_voltage", {
                "name": "Battery voltage",
                "device_class": "voltage",
                "unit_of_measurement": "V",
                "state_class": "measurement",
                "entity_category": "diagnostic",
                "value_template": "{{ value_json.battery_v }}",
                **common,
            }),
            self._cfg("sensor", f"coop_{cid}_next_close", f"{cid}_next_close", {
                "name": "Next close",
                "device_class": "timestamp",
                "value_template": "{{ value_json.next_close }}",
                **common,
            }),
            self._cfg("sensor", f"coop_{cid}_next_open", f"{cid}_next_open", {
                "name": "Next open",
                "device_class": "timestamp",
                "value_template": "{{ value_json.next_open }}",
                **common,
            }),
        ]

    def solar_configs(self, solar: SolarStatus) -> list[tuple[str, dict[str, Any]]]:
        sid = solar.id.replace("-", "_")
        state_t = f"solar/{solar.id}/state"
        dev = self._device(f"solar_{sid}", solar.name, "Solar charge controller" + (" (simulated)" if solar.simulated else ""))
        common = {
            "state_topic": state_t,
            "availability_topic": state_t,
            "availability_template": _ONLINE_FROM_JSON,
            "device": dev,
        }

        def sensor(key: str, name: str, field: str, **extra: Any) -> tuple[str, dict[str, Any]]:
            return self._cfg("sensor", f"solar_{sid}_{key}", f"{sid}_{key}", {
                "name": name,
                "value_template": f"{{{{ value_json.{field} }}}}",
                **extra,
                **common,
            })

        return [
            sensor("soc", "Battery", "battery_soc", device_class="battery", unit_of_measurement="%",
                   state_class="measurement"),
            sensor("battery_v", "Battery voltage", "battery_v", device_class="voltage", unit_of_measurement="V",
                   state_class="measurement", suggested_display_precision=2),
            sensor("battery_a", "Battery current", "battery_a", device_class="current", unit_of_measurement="A",
                   state_class="measurement"),
            sensor("panel_w", "Panel power", "panel_w", device_class="power", unit_of_measurement="W",
                   state_class="measurement"),
            sensor("panel_v", "Panel voltage", "panel_v", device_class="voltage", unit_of_measurement="V",
                   state_class="measurement", entity_category="diagnostic"),
            sensor("load_w", "Load power", "load_w", device_class="power", unit_of_measurement="W",
                   state_class="measurement"),
            # total_increasing + daily reset is what the HA Energy dashboard expects.
            sensor("yield_today", "Yield today", "yield_today_wh", device_class="energy", unit_of_measurement="Wh",
                   state_class="total_increasing"),
            sensor("charge_state", "Charge state", "charge_state", device_class="enum", icon="mdi:solar-power",
                   options=["off", "bulk", "absorption", "float", "fault"]),
        ]

    # ---------------------------------------------------------------- helpers

    def _send(self, topic: str, payload: dict[str, Any]) -> None:
        self._publish(topic, json.dumps(payload, separators=(",", ":")), True)
