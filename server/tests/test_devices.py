"""Tests for the coop/solar device registry and the simulator."""

import random
from datetime import datetime, timedelta

from gate_monitor import simulator as sim_mod
from gate_monitor.devices import CoopStatus, DeviceRegistry, SolarStatus, valid_device_id
from gate_monitor.simulator import DeviceSimulator
from gate_monitor.sun import sun_times


class TestRegistry:
    def test_creates_device_and_notifies(self) -> None:
        reg = DeviceRegistry()
        seen = []
        reg.add_callback(seen.append)
        dev = reg.update("coop", "main-coop", {"door": "open", "temperature_c": 12.5})
        assert isinstance(dev, CoopStatus)
        assert dev.door == "OPEN"  # normalised to upper case
        assert dev.online is True  # a state message implies online
        assert dev.name == "Main Coop"  # derived from id when not given
        assert seen == [dev]

    def test_identical_update_is_silent(self) -> None:
        reg = DeviceRegistry()
        seen = []
        reg.add_callback(seen.append)
        payload = {"door": "CLOSED", "last_update": "2026-01-01T00:00:00+00:00"}
        reg.update("coop", "c1", payload)
        reg.update("coop", "c1", payload)  # e.g. simulator + MQTT echo
        assert len(seen) == 1

    def test_unknown_values_are_coerced(self) -> None:
        reg = DeviceRegistry()
        coop = reg.update("coop", "c1", {"door": "SIDEWAYS"})
        solar = reg.update("solar", "s1", {"charge_state": "Turbo"})
        assert coop.door == "UNKNOWN"
        assert isinstance(solar, SolarStatus) and solar.charge_state == "fault"

    def test_ignores_unknown_fields_and_bad_ids(self) -> None:
        reg = DeviceRegistry()
        dev = reg.update("solar", "s1", {"panel_w": 120.0, "rogue": 1})
        assert not hasattr(dev, "rogue")
        assert reg.update("solar", "../etc", {}) is None
        assert reg.update("toaster", "t1", {}) is None

    def test_id_validation(self) -> None:
        assert valid_device_id("barn-solar")
        assert valid_device_id("coop_2")
        assert not valid_device_id("Coop")  # upper case
        assert not valid_device_id("a/b")
        assert not valid_device_id("")
        assert not valid_device_id("x" * 40)

    def test_of_kind(self) -> None:
        reg = DeviceRegistry()
        reg.update("coop", "a", {})
        reg.update("solar", "b", {})
        assert [d.id for d in reg.of_kind("coop")] == ["a"]


class TestSun:
    def test_sunrise_before_sunset_and_plausible(self) -> None:
        day = datetime(2026, 6, 21).date()
        rise, set_ = sun_times(day, 40.0, -105.0)
        assert rise < set_
        length_h = (set_ - rise).total_seconds() / 3600
        assert 14.5 < length_h < 15.5  # ~15h at 40N on the solstice


class TestSimulator:
    def _run(self, sim: DeviceSimulator, start: datetime, hours: float, step_s: float = 30.0):
        doors = []
        t = start
        end = start + timedelta(hours=hours)
        while t < end:
            sim.tick(t, step_s)
            d = sim.coops["main-coop"].door
            if not doors or doors[-1][1] != d:
                doors.append((t, d))
            t += timedelta(seconds=step_s)
        return doors

    def test_door_follows_schedule(self, monkeypatch) -> None:
        monkeypatch.setattr(sim_mod, "JAM_CHANCE", 0.0)
        random.seed(0)
        out = []
        sim = DeviceSimulator(lambda *a: out.append(a), 40.0, -105.0)
        start = datetime.now().astimezone()
        doors = self._run(sim, start, 48)
        states = [d for _, d in doors]
        # Over 48h the door must have both opened and closed on its own.
        assert "OPENING" in states and "CLOSING" in states
        assert {"OPEN", "CLOSED"} <= set(states)

    def test_manual_close_holds_until_next_transition(self, monkeypatch) -> None:
        monkeypatch.setattr(sim_mod, "JAM_CHANCE", 0.0)
        sim = DeviceSimulator(lambda *a: None, 40.0, -105.0)
        # Tomorrow, so the simulated clock is always ahead of the simulator's start.
        tomorrow = datetime.now().astimezone() + timedelta(days=1)
        rise, _ = sun_times(tomorrow.date(), 40.0, -105.0)
        noon = rise + timedelta(hours=4)
        # The schedule should open the door on its own first...
        for i in range(0, 600, 30):
            sim.tick(noon + timedelta(seconds=i), 30)
        assert sim.coops["main-coop"].door == "OPEN"
        # ...then a manual close must not be undone by the schedule.
        sim.handle_command("main-coop", "CLOSE")
        for i in range(600, 3600, 30):
            sim.tick(noon + timedelta(seconds=i), 30)
        assert sim.coops["main-coop"].door == "CLOSED"

    def test_manual_mode_and_commands(self) -> None:
        sim = DeviceSimulator(lambda *a: None, 40.0, -105.0)
        assert sim.handle_command("main-coop", "MANUAL")
        assert sim.coops["main-coop"].mode == "manual"
        assert not sim.handle_command("main-coop", "LAUNCH")
        assert not sim.handle_command("barn-solar", "OPEN")  # solar takes no commands
        assert sim.owns("barn-solar") and not sim.owns("nope")

    def test_solar_bounds(self) -> None:
        out = []
        sim = DeviceSimulator(lambda k, i, p: out.append(p) if k == "solar" else None, 40.0, -105.0)
        t = datetime.now().astimezone()
        for i in range(0, 24 * 3600, 120):
            sim.tick(t + timedelta(seconds=i), 120)
        assert all(0 <= p["battery_soc"] <= 100 for p in out)
        assert all(p["panel_w"] >= 0 for p in out)
        assert {p["charge_state"] for p in out} <= {"off", "bulk", "absorption", "float"}
        assert max(p["panel_w"] for p in out) > 0  # the sun came up
