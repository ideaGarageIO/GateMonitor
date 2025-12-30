# Gate Monitor

LoRa-based IoT system for remote monitoring and control of a motorized sliding gate.

## Overview

This project uses two Heltec ESP32 LoRa V3 boards to communicate over 915MHz LoRa, with a Raspberry Pi serving as the web interface for monitoring and control.

### Architecture

```
[Gate Node]  ──LoRa 915MHz──  [House Gateway]  ──MQTT──  [Raspberry Pi]
  ESP32 V3                       ESP32 V3                  Web Server
  - Limit switches               - LoRa ↔ WiFi bridge      - Mosquitto
  - Optocoupler control          - MQTT publisher          - Dashboard
  - Deep sleep                                             - Real-time UI
  - Battery monitoring
```

## Project Structure

```
GateMonitor/
├── firmware/               # Arduino sketches for ESP32 boards
│   ├── gate_node/          # Gate-side ESP32 (sensor + control)
│   ├── house_gateway/      # House-side ESP32 (LoRa-MQTT bridge)
│   └── lib/                # Shared libraries
│       └── gate_protocol/  # Common message protocol
├── server/                 # Raspberry Pi web server
│   ├── src/gate_monitor/   # Python FastAPI application
│   ├── static/             # Frontend (HTML/CSS/JS)
│   └── tests/              # Server tests
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

### 2. Set Up Raspberry Pi

```bash
cd server

# Install dependencies (using uv)
uv sync

# Configure MQTT broker
sudo cp ../config/mosquitto/gate_monitor.conf /etc/mosquitto/conf.d/

# Run the server
uv run gate-monitor
```

### 3. Access Dashboard

Open `http://<raspberry-pi-ip>:8000` in your browser.

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

## Development

### Firmware Development

Requires Arduino IDE with Heltec ESP32 board support:
- Board: `Heltec WiFi LoRa 32(V3)`
- Library: `HelTecAutomation/Heltec_ESP32`

### Server Development

```bash
cd server
uv sync --dev
uv run pytest
```

## License

MIT License - See [LICENSE](LICENSE)

## Author

Cameron Owens
