# Gate Monitor

LoRa-based IoT system for remote monitoring and control of a motorized sliding
gate, growing into a farm monitor: chicken coop doors and solar charge status
(simulated until that hardware exists), a live React dashboard, and Home
Assistant integration for phone control.

## Overview

This project uses two Heltec ESP32 LoRa V3 boards to communicate over 915MHz LoRa, with a Raspberry Pi serving as the web interface for monitoring and control.

### Architecture

```
[Gate Node]  ──LoRa 915MHz──  [House Gateway]  ──MQTT──  [Home server (Docker)]
  ESP32 V3                       ESP32 V3                  - Mosquitto broker
  - Limit switches               - LoRa ↔ WiFi bridge      - Gate Monitor: React dashboard,
  - Optocoupler control          - MQTT publisher            history, coop/solar simulator
  - Deep sleep                                             - Home Assistant: phone app,
  - Battery monitoring                                       alerts, automations
```

## Project Structure

```
GateMonitor/
├── firmware/               # Arduino sketches for ESP32 boards
│   ├── gate_node/          # Gate-side ESP32 (sensor + control)
│   ├── house_gateway/      # House-side ESP32 (LoRa-MQTT bridge)
│   └── lib/                # Shared libraries
│       └── gate_protocol/  # Common message protocol
├── server/                 # Web server
│   ├── src/gate_monitor/   # Python FastAPI application
│   ├── frontend/           # React + TypeScript dashboard (Vite)
│   ├── scripts/            # Mock gateway, retained-message cleanup
│   └── tests/              # Server tests
├── deploy/                 # Docker Compose + Home Assistant config for the home server
├── scripts/                # provision-home-server.sh, ha_bootstrap.py, legacy Pi setup
├── hardware/               # Hardware design files
│   ├── schematics/         # Circuit schematics
│   └── pcb/                # PCB designs (Flux.ai/KiCad)
├── config/                 # Configuration templates
│   └── mosquitto/          # MQTT broker config
└── docs/                   # Documentation
```

## Hardware Requirements

- 2x Heltec WiFi LoRa 32 V3 (ESP32-S3 + SX1262)
- Raspberry Pi (3B+ or newer)
- Apollo 635 gate controller
- 12V marine battery with solar charging
- 5dBi LoRa antennas with U.FL cables
- PC817 optocouplers for gate control interface
- Buck converter (12V → 5V)

## Quick Start

### 1. Flash Firmware

```bash
# Using Arduino IDE or arduino-cli
# See firmware/README.md for detailed instructions
```

### 2. Provision the home server

```bash
sudo ./scripts/provision-home-server.sh --lat <lat> --lon <lon> --country US \
     --ha-user farm --ha-password '<password>'
```

This installs Docker, Mosquitto (with passwords), Home Assistant and Gate
Monitor, then prints the MQTT credentials for the gateway firmware. See
[deploy/README.md](deploy/README.md), including how to migrate from the old
native Pi setup.

### 3. Use it

- Dashboard: `http://<server-ip>:8000`, with Overview / Gate / Coops / Solar tabs and live charts
- Home Assistant: `http://<server-ip>:8123`, plus the Companion app on your phone, the
  **Farm** dashboard and lock-screen "Close gate" alerts

For development without hardware, see [server/README.md](server/README.md).

## Communication Protocol

### LoRa Messages (Gate ↔ Gateway)

| Type | Direction | Format | Description |
|------|-----------|--------|-------------|
| STATUS | Gate → GW | `S\|<state>\|<battery_mv>\|<seq>` | Gate state update |
| HEARTBEAT | Gate → GW | `H\|<state>\|<battery_mv>\|<seq>` | Periodic keepalive |
| COMMAND | GW → Gate | `C\|<cmd>\|<seq>` | Control command |
| ACK | Both | `A\|<seq>` | Acknowledgment |

### MQTT Topics

| Topic | Direction | Payload |
|-------|-----------|---------|
| `gate/status` | Gateway → Server | JSON status object |
| `gate/command` | Server → Gateway | `OPEN`, `CLOSE`, `STOP` |
| `gate/battery` | Gateway → Server | Battery voltage (mV) |
| `coop/<id>/state`, `solar/<id>/state` | Device → Server | JSON (see docs) |

Full contract, including the coop/solar payloads for future hardware and the
Home Assistant discovery topics: [docs/mqtt-topics.md](docs/mqtt-topics.md).

## Development

### Firmware Development

Requires Arduino IDE with Heltec ESP32 board support:
- Board: `Heltec WiFi LoRa 32(V3)`
- Library: `HelTecAutomation/Heltec_ESP32`

### Server Development

```bash
cd server
uv sync --group dev
uv run pytest
uv run gate-monitor & uv run python scripts/mock_gateway.py   # full stack, no hardware
```

## License

MIT License - See [LICENSE](LICENSE)

## Author

Cameron Owens
