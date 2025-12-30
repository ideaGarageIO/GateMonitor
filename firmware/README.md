# Gate Monitor Firmware

Arduino sketches for the Heltec ESP32 LoRa V3 boards.

## Structure

```
firmware/
├── gate_node/          # Gate-side ESP32
│   ├── gate_node.ino
│   └── gate_protocol.h
├── house_gateway/      # House-side ESP32
│   ├── house_gateway.ino
│   └── gate_protocol.h
└── lib/
    └── gate_protocol/  # Shared protocol (source of truth)
```

## Requirements

### Arduino IDE Setup

1. **Add Heltec Board Manager URL**
   - Open Arduino IDE → Preferences
   - Add to "Additional Board Manager URLs":
     ```
     https://github.com/Heltec-Aaron-Lee/WiFi_Kit_series/releases/download/0.0.9/package_heltec_esp32_index.json
     ```

2. **Install Board Package**
   - Tools → Board → Boards Manager
   - Search "Heltec ESP32"
   - Install "Heltec ESP32 Series Dev-boards"

3. **Select Board**
   - Tools → Board → Heltec ESP32 Arduino → WiFi LoRa 32(V3)

4. **Install Libraries**
   - The Heltec library includes LoRa and display support
   - For house_gateway, also install: `PubSubClient` (MQTT)

## Flashing

### Gate Node

1. Open `gate_node/gate_node.ino`
2. Connect ESP32 via USB-C
3. Select correct port (Tools → Port)
4. Click Upload

### House Gateway

1. Open `house_gateway/house_gateway.ino`
2. **Edit WiFi credentials** at top of file:
   ```cpp
   const char* WIFI_SSID = "YOUR_WIFI_SSID";
   const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   ```
3. **Edit MQTT server IP**:
   ```cpp
   const char* MQTT_SERVER = "192.168.1.100";  // Raspberry Pi IP
   ```
4. Connect ESP32 via USB-C
5. Select correct port
6. Click Upload

## GPIO Pin Assignments

### Gate Node

| Pin | Function | Notes |
|-----|----------|-------|
| GPIO 5 | Limit Switch (Open) | Active LOW, internal pullup |
| GPIO 6 | Limit Switch (Closed) | Active LOW, internal pullup |
| GPIO 7 | Control Output (Open) | To optocoupler |
| GPIO 8 | Control Output (Close) | To optocoupler |
| GPIO 1 | Battery ADC | Via voltage divider |

### House Gateway

Uses WiFi and LoRa only - no additional GPIO required.

## Protocol

See `lib/gate_protocol/README.md` for message format details.

## Testing

### Serial Monitor

Set baud rate to 115200 to view debug output.

### Validate Communication

1. Flash both boards
2. Power on gate_node first
3. Power on house_gateway
4. Monitor serial output for message exchange
5. Verify MQTT messages on Raspberry Pi:
   ```bash
   mosquitto_sub -h localhost -t "gate/#" -v
   ```
