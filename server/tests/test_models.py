"""Tests for gate monitor data models."""

import pytest

from gate_monitor.models import Command, GateState, GateStatus


class TestGateState:
    """Tests for the GateState enumeration."""

    def test_string_representation(self) -> None:
        """GateState should convert to its name as a string."""
        assert str(GateState.CLOSED) == "CLOSED"
        assert str(GateState.OPEN) == "OPEN"
        assert str(GateState.MOVING) == "MOVING"
        assert str(GateState.ERROR) == "ERROR"
        assert str(GateState.UNKNOWN) == "UNKNOWN"

    def test_integer_values(self) -> None:
        """GateState values should match protocol definitions."""
        assert int(GateState.UNKNOWN) == 0
        assert int(GateState.CLOSED) == 1
        assert int(GateState.OPEN) == 2
        assert int(GateState.MOVING) == 3
        assert int(GateState.ERROR) == 4


class TestCommand:
    """Tests for the Command enumeration."""

    def test_from_string_valid_lowercase(self) -> None:
        """Command.from_string should parse lowercase command strings."""
        assert Command.from_string("open") == Command.OPEN
        assert Command.from_string("close") == Command.CLOSE
        assert Command.from_string("stop") == Command.STOP
        assert Command.from_string("status") == Command.STATUS

    def test_from_string_valid_uppercase(self) -> None:
        """Command.from_string should parse uppercase command strings."""
        assert Command.from_string("OPEN") == Command.OPEN
        assert Command.from_string("CLOSE") == Command.CLOSE
        assert Command.from_string("STOP") == Command.STOP
        assert Command.from_string("STATUS") == Command.STATUS

    def test_from_string_valid_mixed_case(self) -> None:
        """Command.from_string should parse mixed case command strings."""
        assert Command.from_string("Open") == Command.OPEN
        assert Command.from_string("ClOsE") == Command.CLOSE

    def test_from_string_invalid(self) -> None:
        """Command.from_string should return None for invalid strings."""
        assert Command.from_string("invalid") is None
        assert Command.from_string("") is None
        assert Command.from_string("opengate") is None

    def test_integer_values(self) -> None:
        """Command values should match protocol definitions."""
        assert int(Command.OPEN) == 1
        assert int(Command.CLOSE) == 2
        assert int(Command.STOP) == 3
        assert int(Command.STATUS) == 4


class TestGateStatus:
    """Tests for the GateStatus dataclass."""

    def test_default_values(self) -> None:
        """GateStatus should have sensible defaults."""
        status = GateStatus()
        assert status.state == GateState.UNKNOWN
        assert status.battery_mv == 0
        assert status.rssi == 0
        assert status.snr == 0
        assert status.online is False

    def test_to_dict_contains_all_fields(self) -> None:
        """to_dict should include all status fields."""
        status = GateStatus(
            state=GateState.CLOSED,
            battery_mv=12600,
            rssi=-85,
            snr=8,
            online=True,
        )
        result = status.to_dict()

        assert result["state"] == "CLOSED"
        assert result["state_code"] == 1
        assert result["battery_mv"] == 12600
        assert result["battery_v"] == 12.6
        assert result["rssi"] == -85
        assert result["snr"] == 8
        assert result["online"] is True
        assert "last_update" in result

    def test_to_dict_battery_conversion(self) -> None:
        """to_dict should correctly convert battery_mv to battery_v."""
        status = GateStatus(battery_mv=11500)
        result = status.to_dict()
        assert result["battery_v"] == 11.5

        status = GateStatus(battery_mv=12345)
        result = status.to_dict()
        assert result["battery_v"] == 12.35  # Rounded to 2 decimal places

    def test_last_update_iso_format(self) -> None:
        """to_dict should format last_update as ISO 8601."""
        status = GateStatus()
        result = status.to_dict()
        # ISO format should contain 'T' separator
        assert "T" in result["last_update"]
