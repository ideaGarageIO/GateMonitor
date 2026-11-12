# Gate Monitor Server

Python web server for the gate monitoring system. Runs on Raspberry Pi.

## Features

- Real-time React + TypeScript dashboard with live telemetry charts (WebSocket)
- MQTT integration with gateway
- Command forwarding to gate
- Status history

## Requirements

- Python 3.10+
- Mosquitto MQTT broker

## Installation

### 1. Install Mosquitto

```bash
sudo apt update
sudo apt install mosquitto mosquitto-clients

# Copy configuration
sudo cp ../config/mosquitto/gate_monitor.conf /etc/mosquitto/conf.d/
sudo systemctl restart mosquitto
```

### 2. Install Python Dependencies

Using [uv](https://github.com/astral-sh/uv) (recommended):

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
cd server
uv sync
```

Or using pip:

```bash
cd server
pip install -e .
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Build the Frontend

The dashboard lives in `frontend/` (React + TypeScript, Vite). It needs Node 20+
(or build it anywhere and copy `frontend/dist/` to the Pi).

```bash
cd server/frontend
npm install
npm run build          # outputs frontend/dist/, served by FastAPI at /
```

No Node on the machine? Build in a container:

```bash
docker run --rm -u $(id -u):$(id -g) -e HOME=/tmp -v "$PWD":/app -w /app \
  node:22-alpine sh -c "npm install && npm run build"
```

If `frontend/dist/` is missing, the server falls back to the legacy page in `static/`.

## Running

### Development

```bash
cd server
uv run gate-monitor

# Or with auto-reload
DEBUG=true uv run gate-monitor
```

### Frontend development (hot reload)

Run the API server, then the Vite dev server, which proxies `/api` and `/ws` to it:

```bash
uv run gate-monitor                 # terminal 1, port 8000
cd frontend && npm run dev          # terminal 2, open http://localhost:5173
```

### Mock gateway (no hardware)

Publishes fake heartbeat + gate status traffic to the broker so the charts move:

```bash
uv run python scripts/mock_gateway.py --interval 1
```

### Production (systemd)

Create `/etc/systemd/system/gate-monitor.service`:

```ini
[Unit]
Description=Gate Monitor Web Server
After=network.target mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/GateMonitor/server
Environment=MQTT_HOST=localhost
ExecStart=/home/pi/.local/bin/uv run gate-monitor
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable gate-monitor
sudo systemctl start gate-monitor
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard |
| `/api/status` | GET | Current gate status |
| `/api/history` | GET | Status history |
| `/api/command/{cmd}` | POST | Send command (open/close/stop) |
| `/ws` | WebSocket | Real-time updates |

## MQTT Topics

| Topic | Direction | Description |
|-------|-----------|-------------|
| `gate/status` | Subscribe | JSON status from gateway |
| `gate/command` | Publish | Commands to gateway |
| `gate/online` | Subscribe | Gate online status |

## Testing

```bash
# Run tests
uv run pytest

# Test MQTT manually
mosquitto_sub -h localhost -t "gate/#" -v
```
