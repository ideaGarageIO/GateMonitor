# LoRa Gate Control System - Project Context

## Project Overview

**Primary Goal**: Remote monitoring and control of a motorized sliding gate located 120 yards from the house on a rural property.

**Secondary Goal**: Learning opportunity for Arduino library programming and LoRa communication protocols, with foundation for future expansion to additional monitoring nodes (chicken coops, well house - planned months to a year away).

**Development Philosophy**: Methodical approach prioritizing reliability and proper hardware integration over quick implementation. Understanding underlying library architecture rather than treating components as black boxes.

## Current Status

### Completed
- ✅ Hardware selection: Heltec ESP32 LoRa V3 boards chosen
- ✅ Architecture decision: Two-node ESP32-to-ESP32 (not LoRaWAN gateway)
- ✅ Antenna solution: 5dBi antennas with U.FL cables
- ✅ Basic communication validated: Ping-pong scripts working
- ✅ Arduino IDE setup with HelTecAutomation/Heltec_ESP32 library
- ✅ Link quality measured: -90 dBm RSSI, +6 dB SNR (adequate for gate control)

### Active Development
- 🔄 Hardware validation with ping-pong communication tests
- 🔄 Learning Arduino library architecture and LoRa protocols

### Next Phase
- 📋 Interface requirements documentation
- 📋 Detailed block diagrams for hardware integration
- 📋 Gate control implementation
- 📋 Custom PCB design for screw terminal interfaces (commercial carrier boards not available)

## Hardware Components

### Communication Nodes
- **Boards**: Heltec WiFi LoRa 32 V3 (ESP32-based)
  - Built-in 128x64 OLED display (SSD1306)
  - LoRa radio (SX1262)
  - Operating frequency: 915MHz
- **Antennas**: 5dBi with U.FL cables
- **Library**: HelTecAutomation/Heltec_ESP32 (https://github.com/HelTecAutomation/Heltec_ESP32)

### Gate Hardware
- **Gate Controller**: Apollo 635
- **Power**: 12V marine battery with solar charging
- **Interface** (planned): Optocoupler relay for 12V signal isolation
- **Power Regulation** (planned): Buck converter for ESP32 power

### Measured Performance
- **Distance**: 120 yards
- **RSSI**: -90 dBm (Fair - adequate with margin)
- **SNR**: +6 dB (Good - reliable communication)
- **Assessment**: Link quality suitable for gate control application

## Technical Architecture

### LoRa Configuration
```cpp
Frequency: 915MHz (915000000 Hz)
Spreading Factor: SF7 (fastest, good for tested distance)
Bandwidth: 125kHz (LORA_BANDWIDTH = 0)
Coding Rate: 4/5 (LORA_CODINGRATE = 1)
TX Power: 14 dBm (can increase to 17-20 dBm if needed)
Preamble Length: 8 symbols
```

### Message Protocol (Current Ping-Pong)
Format: `TYPE|BOARD_ID|timestamp|count`
- Example: `PING|BOARD_A|12345|5`
- Example: `PONG|BOARD_B|67890|3`

### System Architecture Decisions

**Why ESP32-to-ESP32 vs LoRaWAN?**
- LoRaWAN requires multi-channel concentrator gateways (complex, expensive)
- Simple point-to-point LoRa sufficient for immediate needs
- Can expand to multiple nodes without LoRaWAN complexity

**Display Integration**
- Uses HT_SSD1306Wire library (I2C communication over Wire.h)
- Vext power pin must be enabled (digitalWrite LOW) before display init
- I2C address: 0x3c, Frequency: 500kHz

**Radio Event Model**
- Event-driven callbacks (not polling):
  - OnTxDone: Transmission complete
  - OnRxDone: Packet received (provides RSSI, SNR)
  - OnTxTimeout: Transmission failed
- State management with `lora_idle` flag prevents concurrent operations
- Must call `Radio.IrqProcess()` in loop to handle events

## Key Arduino Library Learnings

### Display Initialization Sequence
```cpp
VextON();                    // Turn on external power (Vext LOW)
delay(100);                  // Power stabilization
display.init();              // Initialize display
display.clear();             // Clear buffer
display.setContrast(255);    // Set brightness
display.display();           // Push to screen
```

### LoRa Radio Initialization
```cpp
Radio.Init(&RadioEvents);    // Register callbacks
Radio.SetChannel(frequency); // Set frequency
Radio.SetTxConfig(...);      // Configure transmit parameters
Radio.SetRxConfig(...);      // Configure receive parameters
Radio.Rx(0);                 // Start receiving (0 = continuous)
```

### I2C Communication (Wire.h)
- Used behind the scenes by display library
- Protocol: Two-wire serial (SDA/SCL)
- Common for sensors, displays, peripherals
- Display library abstracts Wire calls

## Future Implementation Plan

### Phase 1: Interface Design (Next)
- Document Apollo 635 gate controller interface requirements
- Create detailed block diagrams showing:
  - ESP32 → Optocoupler → Gate Controller signal flow
  - Power architecture (12V battery → Buck → ESP32)
  - Antenna connections
- Design custom PCB for proper screw terminal interfaces
  - Tool choice: Flux.ai (AI-powered, accepts natural language)

### Phase 2: Gate Control Logic
- Replace ping-pong with gate control commands
- Implement security measures (authentication, encryption)
- ACK/retry logic with 30-second timeouts
- Command set: OPEN, CLOSE, STOP, STATUS
- Status monitoring: Gate position, battery voltage, errors

### Phase 3: Power Management
- Deep sleep cycles for battery conservation
- Wake on LoRa interrupt
- Solar charging monitoring

### Phase 4: Home Automation Integration
- MQTT connectivity for Home Assistant/etc
- RESTful API for local control
- Web interface for monitoring

### Phase 5: Expansion (Months to Year Away)
- Additional monitoring nodes:
  - Chicken coop environmental monitoring
  - Well house monitoring
- Multi-node communication architecture

## Development Workflow Preferences

### Mode-Based Development
1. **Planning**: Brainstorm, weigh design choices, block diagrams, design justification
2. **Design Review**: Edge cases, failure modes, unforeseen consequences
3. **Software Development**: Implementation after design is solid
4. **Documentation**: README, Sphinx docs, Google Docs for socialization

### Code Preferences
- **Languages**: C/C++, Python, ROS, Shell (embedded/robotics focus)
- **Design patterns**: Single inheritance, clear class definitions, clear ownership
- **Testing**: pytest (Python), gtest (C++), manual test scripts
- **Python**: UV package manager, pyproject.toml
- **Documentation**: Sphinx for project docs, README.md for basics

### Code Style
- Concise variable names in embedded context (i, j, e, el)
- Clear class interfaces
- Unit tests after classes/objects finalized

## Component Selection Methodology

1. Research multiple options for each component
2. Seek specific product compatibility verification
3. Validate with simple tests before complex implementation
4. Document rationale for choices
5. Maintain flexibility for future expansion
6. Consider cost-effective alternatives

## Resources and References

### Libraries Used
- **Heltec ESP32**: HelTecAutomation/Heltec_ESP32
- **Display**: HT_SSD1306Wire (included with Heltec library)
- **LoRa**: LoRaWan_APP.h (included with Heltec library)
- **I2C**: Wire.h (Arduino standard library)

### Hardware Documentation
- Heltec ESP32 V3: https://heltec.org/project/wifi-lora-32-v3/
- Apollo 635: (gate controller documentation)

### Design Tools
- **PCB Design**: Flux.ai (AI-powered, natural language interface)
- **Documentation**: Sphinx
- **Arduino IDE**: Version 2.x

## Current Working Code

Two ping-pong test sketches validate hardware:
- **PING Board (Board A)**: Sends PING every 2 seconds, displays TX count and PONG responses
- **PONG Board (Board B)**: Listens for PING, responds with PONG, displays RX/TX counts

Both display RSSI and SNR values for link quality monitoring.

## Project File Structure (Recommended)

```
~/lora-gate-project/
├── README.md                    # Project overview
├── PROJECT_CONTEXT.md           # This file
├── docs/                        # Sphinx documentation
├── sketches/                    # Arduino code
│   ├── ping_board/
│   │   └── ping_board.ino
│   ├── pong_board/
│   │   └── pong_board.ino
│   └── gate_control/           # Future implementation
├── hardware/                    # Hardware design files
│   ├── block_diagrams/
│   ├── schematics/
│   └── pcb/                    # Flux.ai designs
├── requirements/                # Interface specs, requirements docs
└── notes/                       # Design decisions, meeting notes
```

## Questions to Address in Next Phase

1. Apollo 635 gate controller interface specifications:
   - Input signal requirements (voltage, current, timing)
   - Output status signals available
   - Wiring diagram

2. Optocoupler relay selection:
   - Voltage/current ratings
   - Switching speed requirements
   - Specific part numbers

3. Power architecture:
   - Buck converter specifications (12V → 3.3V/5V)
   - Current draw measurements (active vs deep sleep)
   - Solar charging integration

4. Security implementation:
   - Authentication method
   - Encryption approach (if needed)
   - Command validation

5. PCB design requirements:
   - Screw terminal specifications
   - Board dimensions/mounting
   - Protection circuitry (ESD, reverse polarity, etc.)

## Link Quality Reference

### RSSI (Received Signal Strength Indicator)
- -30 to -60 dBm: Excellent
- -60 to -75 dBm: Very Good
- -75 to -85 dBm: Good
- **-85 to -95 dBm: Fair** ← Current: -90 dBm
- -95 to -105 dBm: Marginal
- -105 to -120 dBm: Very Poor

### SNR (Signal-to-Noise Ratio)
- SNR > 10 dB: Excellent
- **SNR 5-10 dB: Good** ← Current: +6 dB
- SNR 0-5 dB: Fair
- SNR < 0 dB: Poor

**Assessment**: Current link quality (-90 dBm, +6 dB SNR) is adequate for reliable gate control. Signal is weak but clean (low noise environment). Has sufficient margin for the application.

## Development Status Summary

**What Works**: Basic LoRa communication validated, hardware functioning, link quality measured and acceptable.

**What's Next**: Move from validation to implementation - design the gate controller interface, create detailed hardware integration plans, develop control logic.

**Timeline**: Taking methodical approach - no rush. Future expansion planned for months to a year away.

**Philosophy**: Understand the why, not just the what. Build foundation correctly for future expansion.
