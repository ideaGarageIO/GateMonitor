# Gate Monitor Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              GATE SITE                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        Gate Controller                            │   │
│  │  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     │   │
│  │  │ Limit Switch │     │ Apollo 635   │     │ Limit Switch │     │   │
│  │  │   (Open)     │────▶│   Board      │◀────│   (Closed)   │     │   │
│  │  └──────────────┘     └──────────────┘     └──────────────┘     │   │
│  │                              │                                    │   │
│  │                              │ Optocoupler                        │   │
│  │                              ▼                                    │   │
│  │  ┌──────────────────────────────────────────────────────────┐   │   │
│  │  │                     Gate Node (ESP32)                      │   │   │
│  │  │  • Monitors limit switches                                 │   │   │
│  │  │  • Controls gate via optocoupler                          │   │   │
│  │  │  • Battery voltage monitoring                              │   │   │
│  │  │  • Deep sleep power management                             │   │   │
│  │  └──────────────────────────────────────────────────────────┘   │   │
│  │                              │                                    │   │
│  └──────────────────────────────│────────────────────────────────────┘   │
│                                 │ LoRa 915MHz                            │
│                                 │ (~120 yards)                           │
└─────────────────────────────────│────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                              HOUSE SITE                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    House Gateway (ESP32)                          │  │
│  │  • LoRa receiver                                                  │  │
│  │  • WiFi connectivity                                              │  │
│  │  • MQTT publisher                                                 │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                 │                                        │
│                                 │ MQTT / WiFi                           │
│                                 ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    Raspberry Pi Server                            │  │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐     │  │
│  │  │  Mosquitto     │  │  FastAPI       │  │  Web Dashboard │     │  │
│  │  │  MQTT Broker   │──│  Backend       │──│  (Browser)     │     │  │
│  │  └────────────────┘  └────────────────┘  └────────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### Gate Node (ESP32 + LoRa)

**Hardware:**
- Heltec WiFi LoRa 32 V3
- PC817 optocouplers (2x) for gate control
- Voltage divider for battery monitoring
- Connection to Apollo 635 limit switches

**Software Functions:**
- Read limit switch states (GPIO 5, 6)
- Detect state changes (debounced)
- Send status updates on change
- Send heartbeat every 30 seconds
- Receive and execute commands
- ACK/retry protocol
- Battery low protection

**Power:**
- 12V from gate battery via buck converter
- Deep sleep between operations (~20µA)
- Wake on LoRa interrupt or timer

### House Gateway (ESP32 + LoRa + WiFi)

**Hardware:**
- Heltec WiFi LoRa 32 V3
- Powered via USB

**Software Functions:**
- Receive LoRa messages from gate
- Parse and validate messages
- Publish to MQTT broker
- Subscribe to command topic
- Forward commands to gate via LoRa
- Track gate online status

### Raspberry Pi Server

**Components:**
- Mosquitto MQTT broker
- FastAPI web server
- Static file serving (dashboard)
- WebSocket for real-time updates

**Software Functions:**
- Subscribe to MQTT status topics
- Broadcast updates via WebSocket
- Serve web dashboard
- Accept commands from dashboard
- Publish commands to MQTT
- Maintain status history

## Communication Protocols

### LoRa Protocol (Gate ↔ Gateway)

**Parameters:**
- Frequency: 915 MHz (US ISM)
- Spreading Factor: SF9
- Bandwidth: 125 kHz
- Coding Rate: 4/5
- TX Power: 14 dBm

**Message Format (ASCII, pipe-delimited):**

| Type | Format | Example |
|------|--------|---------|
| STATUS | `S\|<state>\|<battery>\|<seq>` | `S\|1\|12600\|42` |
| HEARTBEAT | `H\|<state>\|<battery>\|<seq>` | `H\|1\|12500\|43` |
| COMMAND | `C\|<cmd>\|<seq>` | `C\|1\|100` |
| ACK | `A\|<seq>` | `A\|42` |

**Reliability:**
- Sequence numbers for message tracking
- ACK required for status/heartbeat
- 3 retries with 5-second timeout
- Command ACK from gate node

### MQTT Protocol (Gateway ↔ Server)

**Topics:**

| Topic | Direction | Payload |
|-------|-----------|---------|
| `gate/status` | Gateway → Server | JSON object |
| `gate/command` | Server → Gateway | `OPEN`, `CLOSE`, `STOP` |
| `gate/battery` | Gateway → Server | Millivolts |
| `gate/online` | Gateway → Server | `online` / `offline` |

**Status JSON:**
```json
{
  "state": "CLOSED",
  "battery": 12600,
  "rssi": -85,
  "snr": 8,
  "online": true
}
```

### WebSocket Protocol (Server ↔ Browser)

**Server → Browser:**
```json
{
  "type": "status",
  "data": {
    "state": "CLOSED",
    "battery_mv": 12600,
    "battery_v": 12.6,
    "rssi": -85,
    "snr": 8,
    "online": true,
    "last_update": "2025-01-01T12:00:00"
  }
}
```

**Browser → Server:**
```json
{
  "type": "command",
  "command": "open"
}
```

## State Machine

### Gate States

```
    ┌─────────┐
    │ UNKNOWN │ (Initial state)
    └────┬────┘
         │ First reading
         ▼
    ┌─────────┐    Open command    ┌────────┐
    │ CLOSED  │───────────────────▶│ MOVING │
    └────┬────┘                    └───┬────┘
         │                             │
         │ Close command               │ Limit switch
         │◀────────────────────────────┤
         │                             │
         │                             ▼
         │                        ┌────────┐
         └───────────────────────▶│  OPEN  │
                                  └────────┘

    ┌────────┐
    │ ERROR  │ (Both switches active or communication failure)
    └────────┘
```

## Security Considerations

### Current (Development)
- No authentication on MQTT
- Local network only
- No encryption

### Planned (Production)
- MQTT username/password
- TLS for MQTT and WebSocket
- Command authentication
- Rate limiting
- Audit logging

## Power Budget

### Gate Node

| State | Current | Duration | Daily Usage |
|-------|---------|----------|-------------|
| Deep Sleep | 20 µA | 23.9 hours | 0.48 mAh |
| Active (LoRa RX) | 12 mA | 1 min | 0.2 mAh |
| TX | 120 mA | 10 sec | 0.3 mAh |
| **Total** | | | **~1 mAh** |

The gate node's power consumption is negligible compared to the Apollo 635 controller (~2-3 Ah/day).
