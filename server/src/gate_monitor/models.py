"""Data models for gate monitor."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional


class GateState(IntEnum):
    UNKNOWN = 0
    CLOSED = 1
    OPEN = 2
    MOVING = 3
    ERROR = 4

    def __str__(self) -> str:
        return self.name


class Command(IntEnum):
    OPEN = 1
    CLOSE = 2
    STOP = 3
    STATUS = 4

    @classmethod
    def from_string(cls, s: str) -> Optional["Command"]:
        mapping = {
            "open": cls.OPEN,
            "close": cls.CLOSE,
            "stop": cls.STOP,
            "status": cls.STATUS,
        }
        return mapping.get(s.lower())


@dataclass
class GateStatus:
    state: GateState = GateState.UNKNOWN
    battery_mv: int = 0
    rssi: int = 0
    snr: int = 0
    online: bool = False
    last_update: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "state": str(self.state),
            "state_code": int(self.state),
            "battery_mv": self.battery_mv,
            "battery_v": round(self.battery_mv / 1000, 2),
            "rssi": self.rssi,
            "snr": self.snr,
            "online": self.online,
            "last_update": self.last_update.isoformat(),
        }


@dataclass
class HistoryEntry:
    timestamp: datetime
    state: GateState
    battery_mv: int

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "state": str(self.state),
            "battery_mv": self.battery_mv,
        }
