"""Database module for storing gate monitor time-series data.

This module provides SQLite-based storage for historical gate data
including battery voltage, signal strength, and state changes.
Uses aiosqlite for async database operations with FastAPI.
"""

import json

import aiosqlite
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "gate_monitor.db"


class Database:
    """Async SQLite database for gate monitor data.

    Stores time-series data for battery voltage, signal quality,
    and gate state changes. Supports querying by time range.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        """Initialize the database.

        Args:
            db_path: Path to SQLite database file. Creates parent
                directories if they don't exist.
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open database connection and create tables if needed."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row
        await self._create_tables()

    async def disconnect(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def _create_tables(self) -> None:
        """Create database tables if they don't exist."""
        await self._connection.executescript("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                battery_mv INTEGER NOT NULL,
                rssi INTEGER NOT NULL,
                snr INTEGER NOT NULL,
                state TEXT NOT NULL,
                online INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_readings_timestamp
                ON readings(timestamp);

            CREATE TABLE IF NOT EXISTS state_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                old_state TEXT,
                new_state TEXT NOT NULL,
                battery_mv INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_state_changes_timestamp
                ON state_changes(timestamp);

            -- Generic telemetry for coops, solar, and future devices.
            -- ts is epoch milliseconds so range queries stay numeric.
            CREATE TABLE IF NOT EXISTS device_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                data TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_device_readings_device_ts
                ON device_readings(device_id, ts);

            -- Human-meaningful events (door opened, gate closed, went offline...)
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                ts INTEGER NOT NULL,
                event TEXT NOT NULL,
                detail TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        """)
        await self._connection.commit()

    async def record_reading(
        self,
        battery_mv: int,
        rssi: int,
        snr: int,
        state: str,
        online: bool,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Record a new sensor reading.

        Args:
            battery_mv: Battery voltage in millivolts.
            rssi: Signal strength in dBm.
            snr: Signal-to-noise ratio in dB.
            state: Current gate state (OPEN, CLOSED, etc.).
            online: Whether the gate is online.
            timestamp: Reading timestamp (defaults to now).

        Returns:
            The ID of the inserted row.
        """
        ts = (timestamp or datetime.now()).isoformat()
        cursor = await self._connection.execute(
            """INSERT INTO readings (timestamp, battery_mv, rssi, snr, state, online)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ts, battery_mv, rssi, snr, state, 1 if online else 0),
        )
        await self._connection.commit()
        return cursor.lastrowid

    async def record_state_change(
        self,
        new_state: str,
        old_state: Optional[str] = None,
        battery_mv: Optional[int] = None,
        timestamp: Optional[datetime] = None,
    ) -> int:
        """Record a gate state change.

        Args:
            new_state: The new gate state.
            old_state: The previous gate state.
            battery_mv: Battery voltage at time of change.
            timestamp: Change timestamp (defaults to now).

        Returns:
            The ID of the inserted row.
        """
        ts = (timestamp or datetime.now()).isoformat()
        cursor = await self._connection.execute(
            """INSERT INTO state_changes (timestamp, old_state, new_state, battery_mv)
               VALUES (?, ?, ?, ?)""",
            (ts, old_state, new_state, battery_mv),
        )
        await self._connection.commit()
        return cursor.lastrowid

    async def get_readings(
        self,
        hours: int = 24,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get recent sensor readings.

        Args:
            hours: Number of hours to look back.
            limit: Maximum number of readings to return.

        Returns:
            List of reading dictionaries with timestamp, battery_mv,
            rssi, snr, state, and online fields.
        """
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor = await self._connection.execute(
            """SELECT timestamp, battery_mv, rssi, snr, state, online
               FROM readings
               WHERE timestamp >= ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (since, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_battery_history(
        self,
        hours: int = 24,
        interval_minutes: int = 5,
    ) -> list[dict[str, Any]]:
        """Get battery voltage history aggregated by interval.

        Args:
            hours: Number of hours to look back.
            interval_minutes: Aggregation interval in minutes.

        Returns:
            List of dictionaries with timestamp, avg_mv, min_mv, max_mv.
        """
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        # SQLite doesn't have great time bucketing, so we'll get raw data
        # and aggregate in Python for simplicity
        cursor = await self._connection.execute(
            """SELECT timestamp, battery_mv
               FROM readings
               WHERE timestamp >= ?
               ORDER BY timestamp ASC""",
            (since,),
        )
        rows = await cursor.fetchall()

        if not rows:
            return []

        # Aggregate into buckets
        buckets: dict[str, list[int]] = {}
        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            # Round to interval
            bucket_ts = ts.replace(
                minute=(ts.minute // interval_minutes) * interval_minutes,
                second=0,
                microsecond=0,
            )
            bucket_key = bucket_ts.isoformat()
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append(row["battery_mv"])

        result = []
        for ts, values in sorted(buckets.items()):
            result.append({
                "timestamp": ts,
                "avg_mv": sum(values) // len(values),
                "min_mv": min(values),
                "max_mv": max(values),
                "avg_v": round(sum(values) / len(values) / 1000, 2),
            })

        return result

    async def get_signal_history(
        self,
        hours: int = 24,
        interval_minutes: int = 5,
    ) -> list[dict[str, Any]]:
        """Get signal strength history aggregated by interval.

        Args:
            hours: Number of hours to look back.
            interval_minutes: Aggregation interval in minutes.

        Returns:
            List of dictionaries with timestamp, avg_rssi, avg_snr.
        """
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor = await self._connection.execute(
            """SELECT timestamp, rssi, snr
               FROM readings
               WHERE timestamp >= ?
               ORDER BY timestamp ASC""",
            (since,),
        )
        rows = await cursor.fetchall()

        if not rows:
            return []

        # Aggregate into buckets
        buckets: dict[str, list[tuple[int, int]]] = {}
        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            bucket_ts = ts.replace(
                minute=(ts.minute // interval_minutes) * interval_minutes,
                second=0,
                microsecond=0,
            )
            bucket_key = bucket_ts.isoformat()
            if bucket_key not in buckets:
                buckets[bucket_key] = []
            buckets[bucket_key].append((row["rssi"], row["snr"]))

        result = []
        for ts, values in sorted(buckets.items()):
            rssi_values = [v[0] for v in values]
            snr_values = [v[1] for v in values]
            result.append({
                "timestamp": ts,
                "avg_rssi": sum(rssi_values) // len(rssi_values),
                "avg_snr": round(sum(snr_values) / len(snr_values), 1),
            })

        return result

    async def get_state_changes(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get recent state changes.

        Args:
            hours: Number of hours to look back.
            limit: Maximum number of changes to return.

        Returns:
            List of state change dictionaries.
        """
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        cursor = await self._connection.execute(
            """SELECT timestamp, old_state, new_state, battery_mv
               FROM state_changes
               WHERE timestamp >= ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (since, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_stats(self, hours: int = 24) -> dict[str, Any]:
        """Get summary statistics for the time period.

        Args:
            hours: Number of hours to analyze.

        Returns:
            Dictionary with battery, signal, and uptime statistics.
        """
        since = (datetime.now() - timedelta(hours=hours)).isoformat()

        cursor = await self._connection.execute(
            """SELECT
                COUNT(*) as count,
                AVG(battery_mv) as avg_battery,
                MIN(battery_mv) as min_battery,
                MAX(battery_mv) as max_battery,
                AVG(rssi) as avg_rssi,
                AVG(snr) as avg_snr,
                SUM(online) as online_count
               FROM readings
               WHERE timestamp >= ?""",
            (since,),
        )
        row = await cursor.fetchone()

        if not row or row["count"] == 0:
            return {
                "hours": hours,
                "reading_count": 0,
                "battery": None,
                "signal": None,
                "uptime_percent": 0,
            }

        return {
            "hours": hours,
            "reading_count": row["count"],
            "battery": {
                "avg_v": round(row["avg_battery"] / 1000, 2) if row["avg_battery"] else 0,
                "min_v": round(row["min_battery"] / 1000, 2) if row["min_battery"] else 0,
                "max_v": round(row["max_battery"] / 1000, 2) if row["max_battery"] else 0,
            },
            "signal": {
                "avg_rssi": round(row["avg_rssi"]) if row["avg_rssi"] else 0,
                "avg_snr": round(row["avg_snr"], 1) if row["avg_snr"] else 0,
            },
            "uptime_percent": round(
                (row["online_count"] / row["count"]) * 100, 1
            ) if row["count"] > 0 else 0,
        }


    # ----------------------------------------------------------- generic API

    async def record_device_reading(self, device_id: str, data: dict[str, Any], ts_ms: int) -> None:
        """Store one telemetry sample (numeric fields only) for any device."""
        numeric = {k: v for k, v in data.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
        await self._connection.execute(
            "INSERT INTO device_readings (device_id, ts, data) VALUES (?, ?, ?)",
            (device_id, ts_ms, json.dumps(numeric, separators=(",", ":"))),
        )
        await self._connection.commit()

    async def get_device_readings(
        self, device_id: str, since_ms: int, max_points: int = 720
    ) -> list[dict[str, Any]]:
        """Readings since ``since_ms``, evenly thinned to at most ``max_points``."""
        cursor = await self._connection.execute(
            "SELECT ts, data FROM device_readings WHERE device_id = ? AND ts >= ? ORDER BY ts ASC",
            (device_id, since_ms),
        )
        rows = await cursor.fetchall()
        step = max(1, -(-len(rows) // max_points))  # ceil division
        picked = rows[::step]
        if rows and picked[-1] is not rows[-1]:
            picked.append(rows[-1])  # always include the newest sample
        return [{"t": row["ts"], **json.loads(row["data"])} for row in picked]

    async def record_event(self, device_id: str, event: str, ts_ms: int, detail: Optional[str] = None) -> None:
        await self._connection.execute(
            "INSERT INTO events (device_id, ts, event, detail) VALUES (?, ?, ?, ?)",
            (device_id, ts_ms, event, detail),
        )
        await self._connection.commit()

    async def get_events(self, device_id: Optional[str] = None, limit: int = 50) -> list[dict[str, Any]]:
        if device_id:
            cursor = await self._connection.execute(
                "SELECT device_id, ts, event, detail FROM events WHERE device_id = ? ORDER BY ts DESC LIMIT ?",
                (device_id, limit),
            )
        else:
            cursor = await self._connection.execute(
                "SELECT device_id, ts, event, detail FROM events ORDER BY ts DESC LIMIT ?", (limit,)
            )
        return [dict(row) for row in await cursor.fetchall()]

    async def prune(self, keep_days: int) -> int:
        """Delete telemetry older than ``keep_days``. Events are kept 4x longer."""
        now_ms = int(datetime.now().timestamp() * 1000)
        cutoff = now_ms - keep_days * 86_400_000
        cur = await self._connection.execute("DELETE FROM device_readings WHERE ts < ?", (cutoff,))
        removed = cur.rowcount
        await self._connection.execute("DELETE FROM events WHERE ts < ?", (now_ms - 4 * keep_days * 86_400_000,))
        await self._connection.commit()
        return removed


# Global database instance
db: Optional[Database] = None


async def get_db() -> Database:
    """Get the global database instance.

    Returns:
        The initialized database instance.

    Raises:
        RuntimeError: If database is not initialized.
    """
    if db is None:
        raise RuntimeError("Database not initialized")
    return db


async def init_db(db_path: Optional[Path] = None) -> Database:
    """Initialize the global database instance.

    Args:
        db_path: Optional custom database path.

    Returns:
        The initialized database instance.
    """
    global db
    db = Database(db_path)
    await db.connect()
    return db


async def close_db() -> None:
    """Close the global database connection."""
    global db
    if db:
        await db.disconnect()
        db = None
