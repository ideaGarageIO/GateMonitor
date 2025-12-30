# Gate Monitor Server

Python web server for the gate monitoring system. Runs on Raspberry Pi.

## Features

- Real-time dashboard with WebSocket updates
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

## Running

### Development

```bash
cd server
uv run gate-monitor

# Or with auto-reload
DEBUG=true uv run gate-monitor
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
