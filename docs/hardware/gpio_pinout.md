# GPIO Pin Assignments

## Gate Node (Heltec ESP32 LoRa V3)

### Input Pins

| GPIO | Function | Connection | Notes |
|------|----------|------------|-------|
| 5 | Limit Switch (Open) | Apollo 635 "Open" limit | Active LOW, internal pullup |
| 6 | Limit Switch (Closed) | Apollo 635 "Closed" limit | Active LOW, internal pullup |
| 1 | Battery ADC | Voltage divider | 12V → 3.3V range |

### Output Pins

| GPIO | Function | Connection | Notes |
|------|----------|------------|-------|
| 7 | Control (Open) | PC817 optocoupler → Apollo "Open" | 500ms pulse |
| 8 | Control (Close) | PC817 optocoupler → Apollo "Close" | 500ms pulse |

### Reserved Pins (Heltec V3)

| Pin | Function |
|-----|----------|
| Vext | External power control (display) |
| SDA_OLED (17) | I2C data (display) |
| SCL_OLED (18) | I2C clock (display) |
| RST_OLED (21) | Display reset |
| LoRa pins | Internal to module |

## Wiring Diagram

```
                    GATE NODE
                  ┌───────────────────────────────────────┐
                  │         Heltec ESP32 LoRa V3          │
                  │                                        │
 12V Battery ─────┤ VIN (via buck converter)              │
                  │                                        │
    GND ──────────┤ GND                                   │
                  │                                        │
                  │ GPIO 5 ◀──── Limit Switch (Open)      │
                  │              │                         │
                  │              └── 10kΩ ─── GND          │
                  │                                        │
                  │ GPIO 6 ◀──── Limit Switch (Closed)    │
                  │              │                         │
                  │              └── 10kΩ ─── GND          │
                  │                                        │
                  │ GPIO 7 ────▶ PC817 ────▶ Apollo OPEN  │
                  │              │                         │
                  │              └── 220Ω ─── 3.3V         │
                  │                                        │
                  │ GPIO 8 ────▶ PC817 ────▶ Apollo CLOSE │
                  │              │                         │
                  │              └── 220Ω ─── 3.3V         │
                  │                                        │
                  │ GPIO 1 ◀──┬── Voltage Divider          │
                  │           │   │                        │
                  │           │   R1 = 10kΩ ─── 12V       │
                  │           │   │                        │
                  │           └── R2 = 3.3kΩ ─── GND      │
                  │                                        │
                  └───────────────────────────────────────┘
```

## Optocoupler Circuit (PC817)

```
        ESP32 GPIO                    Apollo 635
            │                             │
            │    ┌─────────────┐         │
            └───▶│ 1   PC817  4 │────────┘ (Open/Close terminal)
                 │             │
            ┌───▶│ 2         3 │────────── (Common/Ground)
            │    └─────────────┘
            │
           220Ω
            │
          3.3V
```

**Notes:**
- Optocoupler provides galvanic isolation between ESP32 and gate controller
- 220Ω resistor limits LED current to ~15mA
- Output is open collector, ties to Apollo 635 terminals

## Battery Voltage Divider

```
    12V Battery
         │
        10kΩ (R1)
         │
         ├──────▶ GPIO 1 (ADC)
         │
        3.3kΩ (R2)
         │
        GND
```

**Calculation:**
- Vout = Vin × R2 / (R1 + R2)
- Vout = 12V × 3.3 / 13.3 = 2.98V (within 3.3V ADC range)
- Ratio = 4.03 (multiply ADC reading by this factor)
- Max input: 13.3V → 3.3V at ADC

## House Gateway (Heltec ESP32 LoRa V3)

The house gateway uses only LoRa and WiFi - no external GPIO required.

| Connection | Notes |
|------------|-------|
| USB-C | Power (5V) and serial debug |
| LoRa Antenna | SMA or U.FL connector |

## Antenna Recommendations

- **Type:** 5dBi omnidirectional
- **Connector:** U.FL to SMA pigtail
- **Mounting:** External to enclosure for best signal
- **Tested Performance:** -90 dBm RSSI, +6 dB SNR at 120 yards
