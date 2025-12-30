"""Tests for gate monitor models."""

import pytest
from gate_monitor.models import Command, GateState, GateStatus


def test_gate_state_string():
    assert str(GateState.CLOSED) == "CLOSED"
    assert str(GateState.OPEN) == "OPEN"
    assert str(GateState.MOVING) == "MOVING"


def test_command_from_string():
    assert Command.from_string("open") == Command.OPEN
    assert Command.from_string("CLOSE") == Command.CLOSE
    assert Command.from_string("Stop") == Command.STOP
    assert Command.from_string("invalid") is None


def test_gate_status_to_dict():
    status = GateStatus(
        state=GateState.CLOSED,
        battery_mv=12600,
        rssi=-85,
        snr=8,
        online=True,
    )

    d = status.to_dict()

    assert d["state"] == "CLOSED"
    assert d["state_code"] == 1
    assert d["battery_mv"] == 12600
    assert d["battery_v"] == 12.6
    assert d["rssi"] == -85
    assert d["snr"] == 8
    assert d["online"] is True
    assert "last_update" in d
