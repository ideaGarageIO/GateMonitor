"""FastAPI application for gate monitor."""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .models import Command, GateStatus
from .mqtt_client import MQTTClient

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# MQTT configuration from environment
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

# Paths
STATIC_DIR = Path(__file__).parent.parent.parent / "static"

# Global state
mqtt_client: Optional[MQTTClient] = None
connected_websockets: set[WebSocket] = set()


async def broadcast_status(status: GateStatus) -> None:
    """Broadcast status update to all connected WebSocket clients."""
    if not connected_websockets:
        return

    message = json.dumps({"type": "status", "data": status.to_dict()})

    # Send to all connected clients
    disconnected = set()
    for ws in connected_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)

    # Remove disconnected clients
    for ws in disconnected:
        connected_websockets.discard(ws)


def on_status_update(status: GateStatus) -> None:
    """Callback for MQTT status updates - schedules async broadcast."""
    asyncio.create_task(broadcast_status(status))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global mqtt_client

    # Startup
    logger.info("Starting Gate Monitor server")

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
        logger.error(f"Failed to connect to MQTT: {e}")

    yield

    # Shutdown
    logger.info("Shutting down Gate Monitor server")
    if mqtt_client:
        mqtt_client.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Gate Monitor",
    description="Web interface for LoRa gate monitoring system",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the main dashboard."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/api/status")
async def get_status():
    """Get current gate status."""
    if mqtt_client:
        return mqtt_client.status.to_dict()
    return {"error": "MQTT not connected"}


@app.get("/api/history")
async def get_history():
    """Get status history."""
    if mqtt_client:
        return [entry.to_dict() for entry in mqtt_client.history]
    return []


@app.post("/api/command/{command}")
async def send_command(command: str):
    """Send a command to the gate."""
    cmd = Command.from_string(command)
    if cmd is None:
        return {"error": f"Invalid command: {command}"}

    if mqtt_client:
        mqtt_client.send_command(cmd)
        return {"status": "sent", "command": command}

    return {"error": "MQTT not connected"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await websocket.accept()
    connected_websockets.add(websocket)
    logger.info(f"WebSocket connected. Total: {len(connected_websockets)}")

    try:
        # Send current status immediately
        if mqtt_client:
            await websocket.send_text(
                json.dumps({"type": "status", "data": mqtt_client.status.to_dict()})
            )

        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "command":
                    cmd = Command.from_string(msg.get("command", ""))
                    if cmd and mqtt_client:
                        mqtt_client.send_command(cmd)
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        pass
    finally:
        connected_websockets.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(connected_websockets)}")


def run():
    """Entry point for the server."""
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
