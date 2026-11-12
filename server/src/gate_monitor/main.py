"""FastAPI application for the farm monitor (gate, coops, solar).

Serves the React dashboard, a REST API and a WebSocket that streams every
status change. Talks to the Mosquitto broker for device data and commands,
and publishes Home Assistant MQTT discovery so the same devices show up in HA.

Threading: paho-mqtt callbacks arrive on its network thread. Everything that
touches application state is hopped onto the asyncio loop with
``call_soon_threadsafe`` / ``run_coroutine_threadsafe``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from gate_monitor import __version__
from gate_monitor.database import Database
from gate_monitor.devices import (
    COOP_COMMANDS,
    DEVICE_KINDS,
    CoopStatus,
    Device,
    DeviceRegistry,
    device_to_dict,
    valid_device_id,
)
from gate_monitor.homeassistant import HomeAssistantDiscovery
from gate_monitor.models import Command, GateState, GateStatus
from gate_monitor.mqtt_client import MQTTClient
from gate_monitor.simulator import DeviceSimulator

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# Configuration from environment
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
SIMULATE_DEVICES = _env_bool("SIMULATE_DEVICES", True)
HA_DISCOVERY = _env_bool("HA_DISCOVERY", True)
HA_DISCOVERY_PREFIX = os.getenv("HA_DISCOVERY_PREFIX", "homeassistant")
PUBLIC_URL = os.getenv("PUBLIC_URL") or None  # shown as "Visit" link on HA device pages
LATITUDE = float(os.getenv("LATITUDE", "40.0"))
LONGITUDE = float(os.getenv("LONGITUDE", "-105.0"))
RECORD_INTERVAL_S = float(os.getenv("RECORD_INTERVAL_S", "15"))
HISTORY_DAYS = int(os.getenv("HISTORY_DAYS", "30"))

SERVER_DIR = Path(__file__).parent.parent.parent
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", SERVER_DIR / "frontend" / "dist"))
STATIC_DIR = SERVER_DIR / "static"  # legacy vanilla-JS page (fallback)
DB_PATH = Path(os.getenv("DB_PATH", SERVER_DIR / "data" / "gate_monitor.db"))

GATE_ID = "gate"


class AppState:
    """Everything the request handlers share. One instance per process."""

    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.mqtt: Optional[MQTTClient] = None
        self.db: Optional[Database] = None
        self.registry = DeviceRegistry()
        self.simulator: Optional[DeviceSimulator] = None
        self.discovery: Optional[HomeAssistantDiscovery] = None
        self.websockets: set[WebSocket] = set()
        self.last_recorded: dict[str, float] = {}
        self.last_gate_state: Optional[GateState] = None
        self.last_gate_online: Optional[bool] = None
        self.last_door: dict[str, str] = {}
        self.background: list[asyncio.Task[Any]] = []


state = AppState()


# ---------------------------------------------------------------- helpers


def now_ms() -> int:
    return int(time.time() * 1000)


def gate_status_dict() -> dict[str, Any]:
    mqtt = state.mqtt
    status = mqtt.status if mqtt else GateStatus()
    data = status.to_dict()
    data["mqtt_connected"] = bool(mqtt and mqtt.is_connected)
    data["gateway_online"] = bool(mqtt and mqtt.is_gateway_online)
    data["last_command"] = mqtt.last_command.name if mqtt and mqtt.last_command else None
    return data


async def broadcast(message: dict[str, Any]) -> None:
    """Send a JSON message to every connected WebSocket; drop dead ones."""
    if not state.websockets:
        return
    text = json.dumps(message)
    dead: list[WebSocket] = []
    for ws in list(state.websockets):
        try:
            await ws.send_text(text)
        except Exception as e:  # noqa: BLE001
            logger.debug("WebSocket send failed: %s", e)
            dead.append(ws)
    for ws in dead:
        state.websockets.discard(ws)


def _spawn(coro: Any) -> None:
    """Fire-and-forget a coroutine on the loop, logging failures."""
    task = asyncio.ensure_future(coro)

    def _done(t: asyncio.Future[Any]) -> None:
        if not t.cancelled() and t.exception() is not None:
            logger.error("Background task failed: %r", t.exception())

    task.add_done_callback(_done)


def _should_record(device_id: str) -> bool:
    now = time.monotonic()
    if now - state.last_recorded.get(device_id, 0.0) < RECORD_INTERVAL_S:
        return False
    state.last_recorded[device_id] = now
    return True


async def _record_event(device_id: str, event: str, detail: Optional[str] = None) -> None:
    ts = now_ms()
    if state.db:
        await state.db.record_event(device_id, event, ts, detail)
    await broadcast({"type": "event", "data": {"device_id": device_id, "ts": ts, "event": event, "detail": detail}})


# ------------------------------------------------------------- gate flow


async def on_gate_status_async() -> None:
    mqtt = state.mqtt
    if mqtt is None:
        return
    status = mqtt.status
    data = gate_status_dict()
    await broadcast({"type": "status", "data": data})

    if state.discovery:
        state.discovery.publish_gate_state(status, mqtt.last_command, mqtt.is_gateway_online)

    # Update the "last seen" markers *before* awaiting: one gateway update
    # arrives as several MQTT messages, and these coroutines interleave.
    prev_state, state.last_gate_state = state.last_gate_state, status.state
    prev_online, state.last_gate_online = state.last_gate_online, status.online
    if prev_state is not None and prev_state != status.state:
        await _record_event(GATE_ID, status.state.name.lower(), f"battery {status.battery_mv / 1000:.2f} V")
    if prev_online is not None and prev_online != status.online:
        await _record_event(GATE_ID, "online" if status.online else "offline")

    if state.db and status.online and status.battery_mv and _should_record(GATE_ID):
        await state.db.record_device_reading(
            GATE_ID,
            {"battery_v": round(status.battery_mv / 1000, 3), "rssi": status.rssi, "snr": status.snr},
            now_ms(),
        )


def on_gate_status(_status: GateStatus) -> None:
    """MQTT client callback — may run on the paho thread or the loop."""
    if state.loop is not None:
        asyncio.run_coroutine_threadsafe(on_gate_status_async(), state.loop)


async def gateway_timeout_checker() -> None:
    """Flag the gateway offline if heartbeats stop (callbacks do the broadcast)."""
    while True:
        await asyncio.sleep(0.5)
        if state.mqtt and state.mqtt.check_gateway_timeout():
            logger.warning("Gateway heartbeat timeout")


# ----------------------------------------------------------- device flow


def on_device_change(device: Device) -> None:
    """Registry callback (always on the loop)."""
    data = device_to_dict(device)
    _spawn(broadcast({"type": "device", "data": data}))
    if state.discovery:
        state.discovery.announce_device(device)

    if isinstance(device, CoopStatus):
        prev = state.last_door.get(device.id)
        if prev != device.door:
            state.last_door[device.id] = device.door
            if prev is not None and device.door not in ("OPENING", "CLOSING"):
                _spawn(_record_event(device.id, device.door.lower()))

    if state.db and device.online and _should_record(device.id):
        _spawn(state.db.record_device_reading(device.id, data, now_ms()))


def handle_device_message(topic: str, payload: str) -> None:
    """``<kind>/<id>/<leaf>`` from MQTT, on the loop."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] not in DEVICE_KINDS:
        return
    kind, device_id, leaf = parts
    if leaf == "state":
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Bad JSON on %s", topic)
            return
        if not isinstance(data, dict):
            return
        if data.get("simulated") and state.simulator is None:
            # Retained leftovers from a previous run with SIMULATE_DEVICES=true.
            return
        state.registry.update(kind, device_id, data)
    elif leaf == "command" and state.simulator and state.simulator.owns(device_id):
        state.simulator.handle_command(device_id, payload)


def simulator_publish(kind: str, device_id: str, payload: dict[str, Any]) -> None:
    """Simulator output: update locally and mirror to MQTT so HA sees it too."""
    state.registry.update(kind, device_id, payload)
    if state.mqtt:
        state.mqtt.publish(f"{kind}/{device_id}/state", json.dumps(payload), retain=True)


def on_mqtt_connect() -> None:
    """paho thread: (re)announce to HA once connected."""
    if state.loop and state.discovery:
        state.loop.call_soon_threadsafe(lambda: state.discovery and state.discovery.announce_all(state.registry.all()))


def on_ha_status(_topic: str, payload: str) -> None:
    if payload.strip().lower() == "online":
        logger.info("Home Assistant came online; republishing discovery")
        on_mqtt_connect()


def send_device_command(device_id: str, command: str) -> dict[str, Any]:
    """Validate and route a command from the web UI or REST API."""
    if device_id == GATE_ID:
        cmd = Command.from_string(command)
        if cmd is None:
            raise HTTPException(400, f"Invalid gate command: {command}")
        if not (state.mqtt and state.mqtt.is_connected):
            raise HTTPException(503, "MQTT not connected")
        state.mqtt.send_command(cmd)
        return {"status": "sent", "device": GATE_ID, "command": cmd.name}

    device = state.registry.get(device_id)
    if device is None:
        raise HTTPException(404, f"Unknown device: {device_id}")
    cmd_str = command.strip().upper()
    if not isinstance(device, CoopStatus) or cmd_str not in COOP_COMMANDS:
        raise HTTPException(400, f"Invalid command for {device_id}: {command}")

    if state.mqtt and state.mqtt.publish(f"coop/{device_id}/command", cmd_str):
        return {"status": "sent", "device": device_id, "command": cmd_str}
    if state.simulator and state.simulator.owns(device_id):
        # No broker: drive the simulator directly so the UI still works.
        state.simulator.handle_command(device_id, cmd_str)
        return {"status": "sent", "device": device_id, "command": cmd_str, "via": "simulator"}
    raise HTTPException(503, "MQTT not connected")


async def prune_loop() -> None:
    while True:
        try:
            if state.db:
                removed = await state.db.prune(HISTORY_DAYS)
                if removed:
                    logger.info("Pruned %d old readings", removed)
        except Exception:  # noqa: BLE001
            logger.exception("Prune failed")
        await asyncio.sleep(6 * 3600)


# -------------------------------------------------------------- lifespan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting Gate Monitor %s (simulate=%s, ha_discovery=%s)", __version__, SIMULATE_DEVICES, HA_DISCOVERY)
    loop = asyncio.get_running_loop()
    state.loop = loop

    try:
        state.db = Database(DB_PATH)
        await state.db.connect()
        logger.info("History database at %s", DB_PATH)
    except Exception:  # noqa: BLE001 - history is optional, live view still works
        logger.exception("Could not open database at %s; history disabled", DB_PATH)
        state.db = None

    mqtt = MQTTClient(host=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASSWORD)
    state.mqtt = mqtt
    mqtt.add_status_callback(on_gate_status)
    for kind in DEVICE_KINDS:
        mqtt.add_topic_handler(
            f"{kind}/", lambda topic, payload: loop.call_soon_threadsafe(handle_device_message, topic, payload)
        )
    mqtt.add_topic_handler("homeassistant/status", on_ha_status)

    if HA_DISCOVERY:
        state.discovery = HomeAssistantDiscovery(
            lambda topic, payload, retain: mqtt.publish(topic, payload, retain=retain),
            prefix=HA_DISCOVERY_PREFIX,
            base_url=PUBLIC_URL,
        )
        mqtt.add_connect_handler(on_mqtt_connect)

    state.registry.add_callback(on_device_change)

    if SIMULATE_DEVICES:
        state.simulator = DeviceSimulator(simulator_publish, LATITUDE, LONGITUDE)
        state.simulator.start()

    mqtt.connect()  # non-blocking; retries until the broker is reachable
    state.background = [
        asyncio.create_task(gateway_timeout_checker()),
        asyncio.create_task(prune_loop()),
    ]

    yield

    logger.info("Shutting down Gate Monitor server")
    for task in state.background:
        task.cancel()
    await asyncio.gather(*state.background, return_exceptions=True)
    if state.simulator:
        await state.simulator.stop()
    mqtt.disconnect()
    if state.db:
        await state.db.disconnect()


app = FastAPI(
    title="Gate Monitor",
    description="Farm monitoring: LoRa gate, chicken coop doors and solar",
    version=__version__,
    lifespan=lifespan,
)


# ------------------------------------------------------------------- API


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "version": __version__,
        "mqtt_connected": bool(state.mqtt and state.mqtt.is_connected),
        "database": state.db is not None,
        "simulator": state.simulator is not None,
        "ha_discovery": state.discovery is not None,
        "websocket_clients": len(state.websockets),
    }


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """Current gate status (kept for backward compatibility)."""
    return gate_status_dict()


@app.get("/api/history")
async def get_history() -> list[dict[str, Any]]:
    """Recent gate status messages held in memory (last 100)."""
    return [entry.to_dict() for entry in state.mqtt.history] if state.mqtt else []


@app.post("/api/command/{command}")
async def send_command(command: str) -> dict[str, Any]:
    """Send a gate command (kept for backward compatibility)."""
    return send_device_command(GATE_ID, command)


@app.get("/api/devices")
async def list_devices() -> dict[str, Any]:
    """Gate status plus every coop and solar device."""
    return {"gate": gate_status_dict(), "devices": [device_to_dict(d) for d in state.registry.all()]}


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str) -> dict[str, Any]:
    if device_id == GATE_ID:
        return gate_status_dict()
    device = state.registry.get(device_id)
    if device is None:
        raise HTTPException(404, f"Unknown device: {device_id}")
    return device_to_dict(device)


@app.post("/api/devices/{device_id}/command/{command}")
async def device_command(device_id: str, command: str) -> dict[str, Any]:
    return send_device_command(device_id, command)


@app.get("/api/readings/{device_id}")
async def get_readings(
    device_id: str,
    minutes: int = Query(60, ge=1, le=60 * 24 * 31),
    max_points: int = Query(720, ge=10, le=5000),
) -> list[dict[str, Any]]:
    """Stored telemetry for charts: ``[{"t": epoch_ms, field: value, ...}]``."""
    if device_id != GATE_ID and not valid_device_id(device_id):
        raise HTTPException(400, "Invalid device id")
    if state.db is None:
        return []
    return await state.db.get_device_readings(device_id, now_ms() - minutes * 60_000, max_points)


@app.get("/api/events")
async def get_events(device: Optional[str] = None, limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
    """Activity log (gate opened, coop door closed, device offline, ...)."""
    if state.db is None:
        return []
    return await state.db.get_events(device, limit)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Real-time stream.

    Server -> client::

        {"type": "status",  "data": {...gate status...}}
        {"type": "devices", "data": [ {...device...}, ... ]}   # once, on connect
        {"type": "device",  "data": {...device...}}            # on every change
        {"type": "event",   "data": {"device_id", "ts", "event", "detail"}}

    Client -> server::

        {"type": "command", "command": "open"}                       # gate
        {"type": "command", "device": "main-coop", "command": "close"}
    """
    await websocket.accept()
    state.websockets.add(websocket)
    logger.info("WebSocket connected. Total: %d", len(state.websockets))
    try:
        await websocket.send_text(json.dumps({"type": "status", "data": gate_status_dict()}))
        await websocket.send_text(
            json.dumps({"type": "devices", "data": [device_to_dict(d) for d in state.registry.all()]})
        )
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict) or msg.get("type") != "command":
                continue
            try:
                result = send_device_command(str(msg.get("device") or GATE_ID), str(msg.get("command", "")))
                await websocket.send_text(json.dumps({"type": "command_result", "data": result}))
            except HTTPException as e:
                await websocket.send_text(
                    json.dumps({"type": "command_result", "data": {"status": "error", "error": e.detail}})
                )
    except WebSocketDisconnect:
        pass
    finally:
        state.websockets.discard(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(state.websockets))


# ------------------------------------------------------------ frontend

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if (FRONTEND_DIST / "index.html").exists():
    # Must be last: serves index.html at "/" plus assets, manifest, icons.
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:

    @app.get("/")
    async def legacy_root() -> Any:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "Frontend not built. Run `npm run build` in server/frontend."}


def run() -> None:
    """Entry point: ``uv run gate-monitor``. HOST/PORT/DEBUG from env."""
    import uvicorn

    uvicorn.run(
        "gate_monitor.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=_env_bool("DEBUG", False),
    )


if __name__ == "__main__":
    run()
