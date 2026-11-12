"""Tests for the generic readings/events storage."""

import time

from gate_monitor.database import Database


async def test_readings_roundtrip_and_thinning(tmp_path) -> None:
    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        base = int(time.time() * 1000) - 100_000
        for i in range(100):
            await db.record_device_reading("s1", {"panel_w": float(i), "charge_state": "bulk", "online": True}, base + i * 1000)
        rows = await db.get_device_readings("s1", base, max_points=10)
        assert len(rows) <= 11
        assert rows[0]["t"] == base
        assert rows[-1]["panel_w"] == 99.0  # newest always included
        assert "charge_state" not in rows[0] and "online" not in rows[0]  # numeric only
        assert await db.get_device_readings("other", base) == []
    finally:
        await db.disconnect()


async def test_events_and_prune(tmp_path) -> None:
    db = Database(tmp_path / "t.db")
    await db.connect()
    try:
        now = int(time.time() * 1000)
        await db.record_event("gate", "open", now - 1000, "x")
        await db.record_event("main-coop", "closed", now)
        assert [e["event"] for e in await db.get_events()] == ["closed", "open"]
        assert [e["device_id"] for e in await db.get_events("gate")] == ["gate"]

        await db.record_device_reading("s1", {"v": 1}, now - 40 * 86_400_000)
        await db.record_device_reading("s1", {"v": 2}, now)
        assert await db.prune(keep_days=30) == 1
        assert [r["v"] for r in await db.get_device_readings("s1", 0)] == [2]
    finally:
        await db.disconnect()
