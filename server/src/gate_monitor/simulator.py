"""Simulated coop doors and solar charge controller.

Stands in for hardware that doesn't exist yet. Produces the same state
payloads (and obeys the same commands) a real device would, so the web UI,
Home Assistant discovery and history all exercise the real code paths.

Enable with ``SIMULATE_DEVICES=true`` (the default while there is no hardware).
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from .sun import daylight_fraction, sun_times

logger = logging.getLogger(__name__)

PublishFn = Callable[[str, str, dict[str, Any]], None]

DOOR_TRAVEL_S = 8.0
TICK_S = 2.0
CLOSE_AFTER_SUNSET = timedelta(minutes=30)
JAM_CHANCE = 0.03  # per automatic close


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone().isoformat() if dt else None


@dataclass
class _Coop:
    id: str
    name: str
    door: str = "CLOSED"
    mode: str = "auto"
    target: Optional[str] = None  # OPEN/CLOSED while moving
    motion_left: float = 0.0
    temperature_c: float = 15.0
    humidity: float = 55.0
    battery_v: float = 12.6
    last_opened: Optional[datetime] = None
    last_closed: Optional[datetime] = None
    jam_pending: bool = False


@dataclass
class _Solar:
    id: str
    name: str
    capacity_wh: float = 12.8 * 100  # 100Ah LiFePO4
    panel_peak_w: float = 400.0
    soc: float = 65.0
    cloud: float = 0.85
    yield_today_wh: float = 0.0
    day: Optional[str] = None
    extra_load_w: float = 0.0
    history: list[float] = field(default_factory=list)


class DeviceSimulator:
    """Drives mock devices on a fixed tick and responds to commands."""

    def __init__(self, publish: PublishFn, latitude: float, longitude: float) -> None:
        self._publish = publish
        self.lat = latitude
        self.lon = longitude
        self.coops = {
            c.id: c
            for c in (
                _Coop("main-coop", "Main Coop", temperature_c=14.0),
                _Coop("brooder", "Brooder", temperature_c=29.0, humidity=48.0),
            )
        }
        self.solar = {s.id: s for s in (_Solar("barn-solar", "Barn Solar"),)}
        self._task: Optional[asyncio.Task[None]] = None
        now = datetime.now().astimezone()
        self._sync_doors_to_schedule(now)
        for coop in self.coops.values():
            coop.temperature_c = self._target_temp(coop, now)

    # ----------------------------------------------------------------- control

    def owns(self, device_id: str) -> bool:
        return device_id in self.coops or device_id in self.solar

    def handle_command(self, device_id: str, command: str) -> bool:
        """Apply a command to a simulated device. Returns False if not applicable."""
        coop = self.coops.get(device_id)
        if coop is None:
            return False
        cmd = command.strip().upper()
        if cmd == "AUTO":
            coop.mode = "auto"
        elif cmd == "MANUAL":
            coop.mode = "manual"
        elif cmd == "STOP":
            if coop.door in ("OPENING", "CLOSING", "JAMMED"):
                coop.door, coop.target, coop.motion_left = "UNKNOWN", None, 0.0
        elif cmd in ("OPEN", "CLOSE"):
            target = "OPEN" if cmd == "OPEN" else "CLOSED"
            if coop.door != target:
                self._start_motion(coop, target, allow_jam=False)
        else:
            return False
        logger.info("Simulator: %s <- %s", device_id, cmd)
        self._emit_coop(coop, datetime.now().astimezone())
        return True

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    # ------------------------------------------------------------------- loop

    async def _run(self) -> None:
        logger.info("Device simulator running (%d coops, %d solar)", len(self.coops), len(self.solar))
        while True:
            try:
                self.tick(datetime.now().astimezone(), TICK_S)
            except Exception:  # noqa: BLE001 - keep simulating
                logger.exception("Simulator tick failed")
            await asyncio.sleep(TICK_S)

    def tick(self, now: datetime, dt: float) -> None:
        moving_w = 0.0
        for coop in self.coops.values():
            self._tick_coop(coop, now, dt)
            if coop.door in ("OPENING", "CLOSING"):
                moving_w += 15.0
        for solar in self.solar.values():
            solar.extra_load_w = moving_w
            self._tick_solar(solar, now, dt)

    # ------------------------------------------------------------------ coops

    def _schedule(self, now: datetime) -> tuple[datetime, datetime]:
        sunrise, sunset = sun_times(now.date(), self.lat, self.lon)
        return sunrise, sunset + CLOSE_AFTER_SUNSET

    def _next_events(self, now: datetime) -> tuple[datetime, datetime]:
        open_at, close_at = self._schedule(now)
        tomorrow_open, tomorrow_close = self._schedule(now + timedelta(days=1))
        next_open = open_at if now < open_at else tomorrow_open
        next_close = close_at if now < close_at else tomorrow_close
        return next_open, next_close

    def _last_transitions(self, now: datetime) -> tuple[datetime, datetime]:
        """Most recent scheduled open and close times at or before ``now``."""
        open_at, close_at = self._schedule(now)
        y_open, y_close = self._schedule(now - timedelta(days=1))
        return (open_at if now >= open_at else y_open), (close_at if now >= close_at else y_close)

    def _sync_doors_to_schedule(self, now: datetime) -> None:
        open_at, close_at = self._schedule(now)
        last_open, last_close = self._last_transitions(now)
        for coop in self.coops.values():
            coop.door = "OPEN" if open_at <= now < close_at else "CLOSED"
            coop.last_opened, coop.last_closed = last_open, last_close

    def _start_motion(self, coop: _Coop, target: str, allow_jam: bool) -> None:
        coop.target = target
        coop.door = "OPENING" if target == "OPEN" else "CLOSING"
        coop.motion_left = DOOR_TRAVEL_S
        coop.jam_pending = allow_jam and target == "CLOSED" and random.random() < JAM_CHANCE

    def _tick_coop(self, coop: _Coop, now: datetime, dt: float) -> None:
        if coop.door in ("OPENING", "CLOSING"):
            coop.motion_left -= dt
            if coop.jam_pending and coop.motion_left < DOOR_TRAVEL_S / 2:
                coop.door, coop.target, coop.jam_pending = "JAMMED", None, False
                logger.warning("Simulator: %s door jammed", coop.id)
            elif coop.motion_left <= 0:
                coop.door = coop.target or "UNKNOWN"
                if coop.door == "OPEN":
                    coop.last_opened = now
                elif coop.door == "CLOSED":
                    coop.last_closed = now
                coop.target = None
        elif coop.mode == "auto" and coop.door in ("OPEN", "CLOSED"):
            # Act on each scheduled transition once; a manual override after a
            # transition holds until the next one.
            last_open, last_close = self._last_transitions(now)
            should_be_open = last_open > last_close
            if should_be_open and coop.door == "CLOSED" and _last_before(coop.last_closed, last_open):
                self._start_motion(coop, "OPEN", allow_jam=False)
            elif not should_be_open and coop.door == "OPEN" and _last_before(coop.last_opened, last_close):
                self._start_motion(coop, "CLOSED", allow_jam=True)

        day = daylight_fraction(now, self.lat, self.lon)
        target = self._target_temp(coop, now)
        coop.temperature_c += (target - coop.temperature_c) * 0.002 * dt + random.uniform(-0.05, 0.05)
        coop.humidity = min(95, max(25, coop.humidity + random.uniform(-0.3, 0.3)))
        coop.battery_v = min(13.4, max(11.6, coop.battery_v + (0.002 if day > 0.2 else -0.001)))
        self._emit_coop(coop, now)

    def _target_temp(self, coop: _Coop, now: datetime) -> float:
        """Indoor-ish climate: follows daylight; the brooder is heated."""
        if coop.id == "brooder":
            return 29.0
        return 8.0 + 12.0 * daylight_fraction(now, self.lat, self.lon)

    def _emit_coop(self, coop: _Coop, now: datetime) -> None:
        next_open, next_close = self._next_events(now)
        self._publish(
            "coop",
            coop.id,
            {
                "name": coop.name,
                "door": coop.door,
                "mode": coop.mode,
                "temperature_c": round(coop.temperature_c, 1),
                "humidity": round(coop.humidity, 1),
                "battery_v": round(coop.battery_v, 2),
                "last_opened": _iso(coop.last_opened),
                "last_closed": _iso(coop.last_closed),
                "next_open": _iso(next_open),
                "next_close": _iso(next_close),
                "online": True,
                "simulated": True,
                "last_update": now.isoformat(),
            },
        )

    # ------------------------------------------------------------------ solar

    def _tick_solar(self, s: _Solar, now: datetime, dt: float) -> None:
        today = now.date().isoformat()
        if s.day != today:
            s.day, s.yield_today_wh = today, 0.0

        s.cloud = min(1.0, max(0.25, s.cloud + random.uniform(-0.03, 0.03)))
        available_w = s.panel_peak_w * daylight_fraction(now, self.lat, self.lon) * s.cloud
        load_w = 22.0 + random.uniform(-2, 2) + s.extra_load_w

        if available_w < 5:
            state, panel_w = "off", 0.0
        elif s.soc < 80:
            state, panel_w = "bulk", available_w
        elif s.soc < 99:
            # Absorption tapers current as the bank fills.
            state, panel_w = "absorption", min(available_w, load_w + (100 - s.soc) * 12)
        else:
            state, panel_w = "float", min(available_w, load_w + 2)

        charge_w = panel_w * 0.96
        net_w = charge_w - load_w
        s.soc = min(100.0, max(0.0, s.soc + net_w * dt / 3600 / s.capacity_wh * 100))
        s.yield_today_wh += charge_w * dt / 3600

        battery_v = 12.9 + 0.5 * (s.soc / 100) + (0.35 if net_w > 0 else 0.0)
        panel_v = 0.0 if available_w < 5 else 18.5 + 2.0 * s.cloud + random.uniform(-0.2, 0.2)

        self._publish(
            "solar",
            s.id,
            {
                "name": s.name,
                "battery_soc": round(s.soc, 1),
                "battery_v": round(battery_v, 2),
                "battery_a": round(net_w / battery_v, 2),
                "panel_v": round(panel_v, 1),
                "panel_w": round(panel_w, 1),
                "load_w": round(load_w, 1),
                "charge_state": state,
                "yield_today_wh": round(s.yield_today_wh, 1),
                "online": True,
                "simulated": True,
                "last_update": now.isoformat(),
            },
        )


def _last_before(event: Optional[datetime], boundary: datetime) -> bool:
    """True if the last event happened before ``boundary`` (i.e. today's transition hasn't run)."""
    return event is None or event < boundary
