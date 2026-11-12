"""API tests with the simulator on and no MQTT broker reachable."""

import os
import tempfile

# Configure before importing the app: unreachable broker, temp DB.
_tmp = tempfile.mkdtemp()
os.environ.update(
    MQTT_HOST="127.0.0.1",
    MQTT_PORT="9",  # discard port: connection refused, client keeps retrying
    DB_PATH=os.path.join(_tmp, "api.db"),
    SIMULATE_DEVICES="true",
    HA_DISCOVERY="true",
    RECORD_INTERVAL_S="0",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gate_monitor.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client) -> None:
    h = client.get("/api/health").json()
    assert h["database"] and h["simulator"] and h["ha_discovery"]
    assert h["mqtt_connected"] is False


def test_devices_listed(client) -> None:
    data = client.get("/api/devices").json()
    ids = {d["id"] for d in data["devices"]}
    assert {"main-coop", "brooder", "barn-solar"} <= ids
    assert data["gate"]["mqtt_connected"] is False


def test_coop_command_falls_back_to_simulator(client) -> None:
    r = client.post("/api/devices/main-coop/command/manual")
    assert r.status_code == 200 and r.json()["via"] == "simulator"
    assert client.get("/api/devices/main-coop").json()["mode"] == "manual"


def test_command_validation(client) -> None:
    assert client.post("/api/devices/barn-solar/command/open").status_code == 400
    assert client.post("/api/devices/nope/command/open").status_code == 404
    assert client.post("/api/devices/gate/command/launch").status_code == 400
    # Valid gate command but no broker -> 503, not a silent success.
    assert client.post("/api/devices/gate/command/open").status_code == 503


def test_readings_and_events(client) -> None:
    assert client.get("/api/readings/barn-solar?minutes=5").status_code == 200
    assert client.get("/api/readings/BAD!").status_code == 400
    assert isinstance(client.get("/api/events").json(), list)


def test_websocket_snapshot_and_command(client) -> None:
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["type"] == "status"
        second = ws.receive_json()
        assert second["type"] == "devices" and len(second["data"]) >= 3
        ws.send_json({"type": "command", "device": "brooder", "command": "auto"})
        for _ in range(20):
            msg = ws.receive_json()
            if msg["type"] == "command_result":
                assert msg["data"]["status"] == "sent"
                break
        else:
            pytest.fail("no command_result")


def test_frontend_served(client) -> None:
    r = client.get("/")
    assert r.status_code == 200
