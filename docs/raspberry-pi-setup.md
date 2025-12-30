# Raspberry Pi Setup Guide

This guide covers the installation and configuration of the Gate Monitor server on a Raspberry Pi.

## Prerequisites

- Raspberry Pi (tested on Pi 3B+, Pi 4, Pi 5)
- Raspberry Pi OS (Bullseye or newer)
- Network connectivity (Ethernet or WiFi)
- SSH access or direct terminal access

## Quick Start

An automated setup script is provided:

```bash
cd /path/to/GateMonitor/scripts
sudo ./setup-raspberry-pi.sh
```

The script installs all dependencies, configures services, and creates a systemd unit for automatic startup.

## Manual Installation

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv mosquitto mosquitto-clients
```

### 2. Configure Mosquitto MQTT Broker

Mosquitto 2.0+ requires explicit listener configuration. Create a config file:

```bash
sudo nano /etc/mosquitto/conf.d/gate-monitor.conf
```

Add the following:

```
listener 1883
allow_anonymous true
```

Restart and enable the service:

```bash
sudo systemctl restart mosquitto
sudo systemctl enable mosquitto
```

Verify it's working:

```bash
mosquitto_pub -h localhost -t test -m "hello"
```

### 3. Set Up Python Environment

Navigate to the server directory and create a virtual environment:

```bash
cd /path/to/GateMonitor/server
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 4. Configure Environment Variables

Create a `.env` file in the server directory:

```bash
nano /path/to/GateMonitor/server/.env
```

Add configuration:

```env
# MQTT Broker settings
MQTT_HOST=localhost
MQTT_PORT=1883
# MQTT_USER=
# MQTT_PASSWORD=

# Web server settings
HOST=0.0.0.0
PORT=8000

# Set to true for development (enables auto-reload)
DEBUG=false
```

### 5. Test the Server

Run the server manually to verify it works:

```bash
cd /path/to/GateMonitor/server
source .venv/bin/activate
python -m gate_monitor.main
```

The web dashboard should be accessible at `http://<pi-ip>:8000`

### 6. Set Up Systemd Service

Create a systemd service file for automatic startup:

```bash
sudo nano /etc/systemd/system/gate-monitor.service
```

Add the following (adjust paths as needed):

```ini
[Unit]
Description=Gate Monitor Web Server
After=network.target mosquitto.service
Requires=mosquitto.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/GateMonitor/server
Environment="PATH=/home/pi/GateMonitor/server/.venv/bin"
ExecStart=/home/pi/GateMonitor/server/.venv/bin/python -m gate_monitor.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gate-monitor
sudo systemctl start gate-monitor
```

## Service Management

| Command | Description |
|---------|-------------|
| `sudo systemctl start gate-monitor` | Start the server |
| `sudo systemctl stop gate-monitor` | Stop the server |
| `sudo systemctl restart gate-monitor` | Restart the server |
| `sudo systemctl status gate-monitor` | Check server status |
| `sudo journalctl -u gate-monitor -f` | View server logs (live) |
| `sudo journalctl -u mosquitto -f` | View MQTT broker logs |

## Troubleshooting

### MQTT Connection Failed (rc=-2)

This error means the gateway cannot connect to the MQTT broker.

**Check if Mosquitto is running:**
```bash
sudo systemctl status mosquitto
```

**Check if Mosquitto is listening on port 1883:**
```bash
sudo ss -tlnp | grep mosquitto
```

**Check Mosquitto logs:**
```bash
sudo cat /var/log/mosquitto/mosquitto.log
# or
sudo journalctl -u mosquitto -n 50
```

**Common fix:** Mosquitto 2.0+ requires explicit listener config. See step 2 above.

### Gateway Not Receiving Messages

Monitor MQTT traffic to verify the house gateway is publishing:

```bash
mosquitto_sub -h localhost -t 'gate/#' -v
```

You should see messages like:
```
gate/status {"state":"CLOSED","battery":12600,"rssi":-85,"snr":8,"online":true}
gate/online online
gate/battery 12600
```

### WebSocket Connection Issues

Check that the server is running and accessible:

```bash
curl http://localhost:8000/api/status
```

Check firewall rules if accessing from another device:

```bash
sudo ufw status
sudo ufw allow 8000
```

### Server Won't Start

Check for Python errors:

```bash
cd /path/to/GateMonitor/server
source .venv/bin/activate
python -m gate_monitor.main
```

Verify all dependencies are installed:

```bash
pip list | grep -E "fastapi|uvicorn|paho-mqtt"
```

## Network Architecture

```
┌────────────────────────────────────────────────────────┐
│                   Raspberry Pi                          │
│                                                         │
│  ┌─────────────────┐     ┌─────────────────────────┐  │
│  │   Mosquitto     │     │   Gate Monitor Server   │  │
│  │   MQTT Broker   │◀───▶│   (FastAPI + WebSocket) │  │
│  │   Port 1883     │     │   Port 8000             │  │
│  └────────┬────────┘     └───────────┬─────────────┘  │
│           │                          │                 │
└───────────│──────────────────────────│─────────────────┘
            │                          │
            │ MQTT                     │ HTTP/WebSocket
            ▼                          ▼
    ┌───────────────┐          ┌───────────────┐
    │ House Gateway │          │  Web Browser  │
    │   (ESP32)     │          │  Dashboard    │
    └───────────────┘          └───────────────┘
```

## Security Considerations

The default setup uses anonymous MQTT access, suitable for local networks. For production:

### Enable MQTT Authentication

1. Create a password file:
   ```bash
   sudo mosquitto_passwd -c /etc/mosquitto/passwd gateway
   ```

2. Update Mosquitto config:
   ```
   listener 1883
   allow_anonymous false
   password_file /etc/mosquitto/passwd
   ```

3. Update `.env` with credentials:
   ```env
   MQTT_USER=gateway
   MQTT_PASSWORD=your_password
   ```

4. Update `credentials.h` on the house gateway with matching credentials.

### Firewall Configuration

Restrict access to trusted networks:

```bash
sudo ufw enable
sudo ufw allow ssh
sudo ufw allow from 192.168.1.0/24 to any port 1883
sudo ufw allow from 192.168.1.0/24 to any port 8000
```
