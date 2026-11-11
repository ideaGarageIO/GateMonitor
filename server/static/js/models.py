"""Data models for gate monitor.

This module defines the core data structures used throughout the gate monitor
application, including gate states, commands, and status tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Optional


class GateState(IntEnum):
    """Enumeration of possible gate states.

    These values match the protocol definitions in the firmware's gate_protocol.h
    to ensure consistent state representation across the system.

    Attributes:
        UNKNOWN: Initial state before first reading.
        CLOSED: Gate is fully closed (closed limit switch active).
        OPEN: Gate is fully open (open limit switch active).
        MOVING: Gate is in motion (neither limit switch active).
        ERROR: Error condition (both limit switches active or communication failure).
    """

    UNKNOWN = 0
    CLOSED = 1
    OPEN = 2
    MOVING = 3
    ERROR = 4

    def __str__(self) -> str:
        """Return the state name as a string.

        Returns:
            The name of the state (e.g., "CLOSED", "OPEN").
        """
        return self.name


class Command(IntEnum):
    """Enumeration of gate control commands.

    These values match the protocol definitions in the firmware's gate_protocol.h
    to ensure consistent command representation across the system.

    Attributes:
        OPEN: Command to open the gate.
        CLOSE: Command to close the gate.
        STOP: Command to stop gate movement.
        STATUS: Request current status from gate node.
    """

    OPEN = 1
    CLOSE = 2
    STOP = 3
    STATUS = 4

    @classmethod
    def from_string(cls, s: str) -> Optional["Command"]:
        """Parse a command from a string.

        Args:
            s: The command string (case-insensitive). Valid values are
               "open", "close", "stop", and "status".

        Returns:
            The corresponding Command enum value, or None if the string
            does not match any valid command.

        Examples:
            >>> Command.from_string("open")
            <Command.OPEN: 1>
            >>> Command.from_string("CLOSE")
            <Command.CLOSE: 2>
            >>> Command.from_string("invalid")
            None
        """
        if not s:
            return None
        mapping = {
            "open": cls.OPEN,
            "close": cls.CLOSE,
            "stop": cls.STOP,
            "status": cls.STATUS,
        }
        return mapping.get(s.lower())


@dataclass
class GateStatus:
    """Current status of the gate.

    This dataclass holds all the real-time information about the gate's
    current state, including position, battery level, and signal quality.

    Attributes:
        state: Current gate state (open, closed, moving, etc.).
        battery_mv: Battery voltage in millivolts.
        rssi: Received Signal Strength Indicator in dBm.
        snr: Signal-to-Noise Ratio in dB.
        online: Whether the gate node is currently online.
        last_update: Timestamp of the last status update.
    """

    state: GateState = GateState.UNKNOWN
    battery_mv: int = 0
    rssi: int = 0
    snr: int = 0
    online: bool = False
    last_update: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert status to a dictionary for JSON serialization.

        Returns:
            A dictionary containing all status fields with JSON-serializable
            values. Includes both raw and derived values (e.g., battery_mv
            and battery_v).

        Examples:
            >>> status = GateStatus(state=GateState.CLOSED, battery_mv=12600)
            >>> status.to_dict()
            {'state': 'CLOSED', 'state_code': 1, 'battery_mv': 12600, ...}
        """
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
    """A single entry in the gate status history.

    Used to track historical gate state changes for display in the
    dashboard's activity log.

    Attributes:
        timestamp: When this state was recorded.
        state: The gate state at this time.
        battery_mv: Battery voltage in millivolts at this time.
    """

    timestamp: datetime
    state: GateState
    battery_mv: int

    def to_dict(self) -> dict[str, Any]:
        """Convert history entry to a dictionary for JSON serialization.

        Returns:
            A dictionary containing the timestamp, state, and battery
            voltage with JSON-serializable values.
        """
        return {
            "timestamp": self.timestamp.isoformat(),
            "state": str(self.state),
            "battery_mv": self.battery_mv,
        }
