"""FastAPI application for gate monitor.

This module provides the web server for the gate monitoring system.
It serves a real-time dashboard via WebSocket and exposes REST API
endpoints for status queries and command submission.

The server connects to an MQTT broker (Mosquitto) to receive gate
status updates from the LoRa gateway and to publish control commands.
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


from gate_monitor.database import close_db, get_db, init_db
from gate_monitor.models import Command, GateStatus
from gate_monitor.mqtt_client import MQTTClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Configuration from environment
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

SERVER_DIR = Path(__file__).parent.parent.parent
# Built React frontend (see frontend/README.md); falls back to the legacy page.
FRONTEND_DIST = SERVER_DIR / "frontend" / "dist"
STATIC_DIR = SERVER_DIR / "static"

# Global state
mqtt_client: Optional[MQTTClient] = None
connected_websockets: set[WebSocket] = set()
last_recorded_state: Optional[str] = None
main_event_loop: Optional[asyncio.AbstractEventLoop] = None


async def broadcast_status(status: GateStatus) -> None:
    """Broadcast a status update to all connected WebSocket clients.

    Sends the status as a JSON message to each connected client.
    Automatically removes clients that have disconnected.

    Args:
        status: The current gate status to broadcast.
    """
    logger.debug("broadcast_status called, %d connected clients", len(connected_websockets))

    if not connected_websockets:
        logger.debug("No connected WebSocket clients, skipping broadcast")
        return

    status_dict = status.to_dict()
    if mqtt_client:
        status_dict["mqtt_connected"] = mqtt_client.is_connected
        status_dict["gateway_online"] = mqtt_client.is_gateway_online
    else:
        status_dict["mqtt_connected"] = False
        status_dict["gateway_online"] = False

    message = json.dumps({"type": "status", "data": status_dict})
    logger.info("Broadcasting status: state=%s, online=%s, gateway_online=%s to %d clients",
                status_dict.get("state"), status_dict.get("online"),
                status_dict.get("gateway_online"), len(connected_websockets))

    disconnected: set[WebSocket] = set()
    for ws in connected_websockets:
        try:
            await ws.send_text(message)
            logger.debug("Sent status to WebSocket client")
        except Exception as e:
            logger.warning("Failed to send to WebSocket: %s", e)
            disconnected.add(ws)

    for ws in disconnected:
        connected_websockets.discard(ws)


def on_status_update(status: GateStatus) -> None:
    """Handle MQTT status updates by scheduling an async broadcast.

    This callback is invoked by the MQTT client when a new status
    message is received. It schedules an asyncio task to broadcast
    the update to all WebSocket clients.

    Note: This is called from the MQTT client's background thread,
    so we use run_coroutine_threadsafe() to schedule on the main loop.

    Args:
        status: The updated gate status from MQTT.
    """
    logger.info("on_status_update called: state=%s, online=%s", status.state, status.online)
    if main_event_loop is not None:
        future = asyncio.run_coroutine_threadsafe(broadcast_status(status), main_event_loop)
        logger.debug("Scheduled broadcast on event loop, future=%s", future)
    else:
        logger.warning("Event loop not available, cannot broadcast status")


async def gateway_timeout_checker() -> None:
    """Background task to check for gateway timeout.

    Runs every 500ms to detect if the gateway has stopped sending heartbeats.
    """
    logger.info("Gateway timeout checker started")
    while True:
        await asyncio.sleep(0.5)  # Check every 500ms
        if mqtt_client:
            changed = mqtt_client.check_gateway_timeout()
            if changed:
                logger.info("Gateway timeout detected!")
                logger.info("Status after timeout: state=%s, online=%s, gateway_online=%s",
                           mqtt_client.status.state, mqtt_client.status.online,
                           mqtt_client.is_gateway_online)
                # Broadcast directly since we're already in the asyncio context
                await broadcast_status(mqtt_client.status)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    On startup, initializes the MQTT client and connects to the broker.
    On shutdown, cleanly disconnects from the broker.

    Args:
        app: The FastAPI application instance.

    Yields:
        None during application runtime.
    """
    global mqtt_client, main_event_loop

    logger.info("Starting Gate Monitor server")

    # Store the event loop for use in MQTT callbacks (which run in a different thread)
    main_event_loop = asyncio.get_running_loop()

    mqtt_client = MQTTClient(
        host=MQTT_HOST,
        port=MQTT_PORT,
        username=MQTT_USER,
        password=MQTT_PASSWORD,
    )
    mqtt_client.add_status_callback(on_status_update)

    try:
        mqtt_client.connect()
    except Exception as e:
        logger.error("Failed to connect to MQTT: %s", e)

    # Start background task to check gateway timeout
    timeout_task = asyncio.create_task(gateway_timeout_checker())
    logger.info("Started gateway timeout checker")

    yield

    logger.info("Shutting down Gate Monitor server")
    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass
    if mqtt_client:
        mqtt_client.disconnect()


app = FastAPI(
    title="Gate Monitor",
    description="Web interface for LoRa gate monitoring system",
    version="0.1.0",
    lifespan=lifespan,
)

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root() -> Any:
    """Serve the main dashboard page.

    Prefers the built React app in frontend/dist, then the legacy static page.

    Returns:
        The index.html file if it exists, otherwise an error dict.
    """
    for index_path in (FRONTEND_DIST / "index.html", STATIC_DIR / "index.html"):
        if index_path.exists():
            return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    """Get the current gate status.

    Returns:
        A dictionary containing the current gate state, battery voltage,
        signal quality, and online status. Returns an error if MQTT is
        not connected.
    """
    if mqtt_client:
        status_dict = mqtt_client.status.to_dict()
        status_dict["mqtt_connected"] = mqtt_client.is_connected
        status_dict["gateway_online"] = mqtt_client.is_gateway_online
        return status_dict
    return {"error": "MQTT not connected", "mqtt_connected": False, "gateway_online": False}


@app.get("/api/history")
async def get_history() -> list[dict[str, Any]]:
    """Get the gate status history.

    Returns:
        A list of historical status entries, each containing timestamp,
        state, and battery voltage. Returns empty list if MQTT is not
        connected.
    """
    if mqtt_client:
        return [entry.to_dict() for entry in mqtt_client.history]
    return []


@app.post("/api/command/{command}")
async def send_command(command: str) -> dict[str, Any]:
    """Send a control command to the gate.

    Args:
        command: The command to send. Valid values are "open", "close",
            "stop", and "status" (case-insensitive).

    Returns:
        A dictionary with status "sent" and the command name on success,
        or an error message if the command is invalid or MQTT is not
        connected.
    """
    cmd = Command.from_string(command)
    if cmd is None:
        return {"error": f"Invalid command: {command}"}

    if mqtt_client:
        mqtt_client.send_command(cmd)
        return {"status": "sent", "command": command}

    return {"error": "MQTT not connected"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time status updates.

    Clients connecting to this endpoint will receive immediate status
    updates whenever the gate state changes. Clients can also send
    commands through the WebSocket connection.

    Args:
        websocket: The WebSocket connection.

    Message Format (server -> client):
        {"type": "status", "data": {...status fields...}}

    Message Format (client -> server):
        {"type": "command", "command": "open|close|stop|status"}
    """
    await websocket.accept()
    connected_websockets.add(websocket)
    logger.info("WebSocket connected. Total: %d", len(connected_websockets))

    try:
        if mqtt_client:
            status_dict = mqtt_client.status.to_dict()
            status_dict["mqtt_connected"] = mqtt_client.is_connected
            status_dict["gateway_online"] = mqtt_client.is_gateway_online
            await websocket.send_text(
                json.dumps({"type": "status", "data": status_dict})
            )

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "command":
                    cmd = Command.from_string(msg.get("command", ""))
                    if cmd and mqtt_client:
                        mqtt_client.send_command(cmd)
            except json.JSONDecodeError:
                logger.debug("Received invalid JSON from WebSocket")

    except WebSocketDisconnect:
        pass
    finally:
        connected_websockets.discard(websocket)
        logger.info("WebSocket disconnected. Total: %d", len(connected_websockets))


def run() -> None:
    """Entry point for running the server.

    Reads configuration from environment variables and starts the
    uvicorn server. Enable DEBUG=true for auto-reload during development.

    Environment Variables:
        HOST: Server bind address (default: 0.0.0.0)
        PORT: Server port (default: 8000)
        DEBUG: Enable auto-reload (default: false)
    """
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        "gate_monitor.main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "false").lower() == "true",
    )


if __name__ == "__main__":
    run()
