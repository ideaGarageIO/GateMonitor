"""Non-gate farm devices: chicken coop doors and solar charge controllers.

Each device publishes a retained JSON document to ``<kind>/<id>/state`` and
accepts plain-text commands on ``<kind>/<id>/command``. The same topic layout
is used by the built-in simulator, so real hardware can replace it without
any server changes.

Topic layout::

    coop/<id>/state     {"name", "door", "mode", "temperature_c", ...}
    coop/<id>/command   OPEN | CLOSE | STOP | AUTO | MANUAL
    solar/<id>/state    {"name", "battery_soc", "battery_v", "panel_w", ...}
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Callable, Literal, Optional, Union

logger = logging.getLogger(__name__)

DeviceKind = Literal["coop", "solar"]
DEVICE_KINDS: tuple[DeviceKind, ...] = ("coop", "solar")

# Device ids become MQTT topic levels and HA unique_ids; keep them boring.
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

COOP_DOOR_STATES = ("UNKNOWN", "OPEN", "CLOSED", "OPENING", "CLOSING", "JAMMED")
COOP_COMMANDS = ("OPEN", "CLOSE", "STOP", "AUTO", "MANUAL")
SOLAR_CHARGE_STATES = ("off", "bulk", "absorption", "float", "fault")


def valid_device_id(device_id: str) -> bool:
    """Return True if ``device_id`` is safe to use as a topic level."""
    return bool(_ID_RE.match(device_id))


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


@dataclass
class CoopStatus:
    """Status of an automatic chicken coop door."""

    id: str
    name: str = ""
    door: str = "UNKNOWN"
    mode: str = "auto"  # "auto" follows the schedule, "manual" ignores it
    temperature_c: Optional[float] = None
    humidity: Optional[float] = None
    battery_v: Optional[float] = None
    last_opened: Optional[str] = None
    last_closed: Optional[str] = None
    next_open: Optional[str] = None
    next_close: Optional[str] = None
    online: bool = False
    last_update: str = field(default_factory=_now_iso)
    simulated: bool = False
    kind: str = field(default="coop", init=False)


@dataclass
class SolarStatus:
    """Status of a solar charge controller and its battery bank."""

    id: str
    name: str = ""
    battery_soc: Optional[float] = None  # percent
    battery_v: Optional[float] = None
    battery_a: Optional[float] = None  # + charging, - discharging
    panel_v: Optional[float] = None
    panel_w: Optional[float] = None
    load_w: Optional[float] = None
    charge_state: str = "off"
    yield_today_wh: Optional[float] = None
    online: bool = False
    last_update: str = field(default_factory=_now_iso)
    simulated: bool = False
    kind: str = field(default="solar", init=False)


Device = Union[CoopStatus, SolarStatus]
_KIND_CLASS: dict[str, type] = {"coop": CoopStatus, "solar": SolarStatus}


def _coerce(device: Device, payload: dict[str, Any]) -> bool:
    """Merge known fields from ``payload`` into ``device``. Returns True if anything changed."""
    changed = False
    for f in fields(device):
        if f.name in ("id", "kind") or f.name not in payload:
            continue
        value = payload[f.name]
        if f.name == "door" and isinstance(value, str):
            value = value.upper()
            if value not in COOP_DOOR_STATES:
                value = "UNKNOWN"
        if f.name == "charge_state" and isinstance(value, str):
            value = value.lower()
            if value not in SOLAR_CHARGE_STATES:
                value = "fault"
        if getattr(device, f.name) != value:
            setattr(device, f.name, value)
            changed = True
    return changed


def device_to_dict(device: Device) -> dict[str, Any]:
    return asdict(device)


class DeviceRegistry:
    """In-memory store of coop and solar devices with change notification."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._callbacks: list[Callable[[Device], None]] = []

    def add_callback(self, cb: Callable[[Device], None]) -> None:
        self._callbacks.append(cb)

    def get(self, device_id: str) -> Optional[Device]:
        return self._devices.get(device_id)

    def all(self) -> list[Device]:
        return sorted(self._devices.values(), key=lambda d: (d.kind, d.name or d.id))

    def of_kind(self, kind: str) -> list[Device]:
        return [d for d in self.all() if d.kind == kind]

    def update(self, kind: str, device_id: str, payload: dict[str, Any]) -> Optional[Device]:
        """Create or update a device from a state payload.

        Notifies callbacks only when a field actually changed, so the same
        state arriving twice (e.g. simulator + MQTT echo) is a no-op.
        """
        cls = _KIND_CLASS.get(kind)
        if cls is None or not valid_device_id(device_id):
            logger.warning("Ignoring state for invalid device %s/%s", kind, device_id)
            return None

        device = self._devices.get(device_id)
        created = False
        if device is None or device.kind != kind:
            device = cls(id=device_id)
            self._devices[device_id] = device
            created = True

        payload = dict(payload)
        payload.setdefault("online", True)
        changed = _coerce(device, payload)
        if not device.name:
            device.name = device_id.replace("-", " ").replace("_", " ").title()
        if created or changed:
            for cb in self._callbacks:
                try:
                    cb(device)
                except Exception:  # noqa: BLE001 - one bad listener must not stop the rest
                    logger.exception("Device callback failed")
        return device
