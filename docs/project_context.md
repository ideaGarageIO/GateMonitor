# Gate Monitoring & Control System - Project Context Summary

**Date:** December 29, 2025  
**Project Owner:** Cameron  
**Target Platform:** Linux development environment

---

## Project Overview

Building a LoRa-based IoT system to remotely monitor and control a motorized sliding gate located 120 yards from the house. This serves both practical automation needs and as a learning opportunity for Arduino library programming and LoRa communication protocols.

### Key Objectives
- Remote monitoring of gate status (open/closed/moving)
- Remote control capability (open/close commands)
- Foundation for future expansion to additional monitoring nodes (chicken coops, well house)
- Reliable outdoor installation with proper power management

---

## Current Hardware

### Gate Controller
- **Model:** Apollo 635/636 control board (referenced in earlier discussions)
- **Note:** Recent link showed GateCrafters GC-2000 - clarification needed on exact model
- **Power:** 12V marine battery with solar charging
- **Existing Access:** 433MHz RF receiver for backup remote access

### LoRa Communication Nodes
- **Boards:** Heltec ESP32 LoRa V3 (currently owned)
  - Link: https://www.amazon.com/Assembled-0-96inch-Bluetooth-Development-Transceiver/dp/B08629526P
  - ESP32-S3 MCU + SX1262 LoRa chip
  - Integrated 0.96" OLED display
  - WiFi, Bluetooth, LoRa (915MHz for USA)
  - Type-C USB interface

### Current Development Status
- **Phase:** Hardware validation and basic communication testing
- **Active Work:** Developing ping-pong communication scripts between two ESP32 boards
- **Goal:** Validate hardware functionality before implementing full gate control system

---

## System Architecture

### Three-Node Design

#### 1. Gate Node (at gate, 120 yards from house)
- ESP32 + LoRa (915MHz)
- Monitors limit switches (fully open, fully closed)
- Controls gate via optocoupler interface to Apollo board
- Deep sleep power management
- Battery voltage monitoring

#### 2. House Gateway
- ESP32 + LoRa + WiFi
- Bridge between LoRa network and home network
- Aggregates data from gate (and future nodes)
- MQTT interface to house computer

#### 3. House Computer
- MQTT broker (Mosquitto)
- Web server for user interface
- Future: Home automation integration

---

## Communication Protocol Design

### LoRa Parameters
- **Frequency:** 915 MHz (US ISM band)
- **Spreading Factor:** SF9 or SF10 (optimized for 120 yard range, ~300ms transmission)
- **Bandwidth:** 125 kHz
- **Coding Rate:** 4/5
- **Protocol:** Bidirectional with ACK/retry logic

### Message Types

**Gate → Gateway:**
- STATUS_UPDATE (on state change only)
- HEARTBEAT (periodic keep-alive)
- ACK (acknowledgment)
- ERROR (fault conditions)

**Gateway → Gate:**
- COMMAND (open/close)
- POLL (request status)
- ACK (acknowledgment)

**Gateway ↔ Computer:**
- MQTT topics: `home/gate/status`, `home/gate/command`

### Timing & Power Management
- **Wake Cycle:** 10 seconds (gate node checks limit switches)
- **Transmission:** Only on state change (power optimization)
- **Timeout:** 30-second timeout for ACK/retry logic
- **Deep Sleep:** ~20 µA between wake cycles

---

## Hardware Interface Design

### Gate Node Outputs (to Apollo 635/636)
- **GPIO 12** → PC817 Optocoupler → OPEN terminal (500ms pulse)
- **GPIO 13** → PC817 Optocoupler → CLOSE terminal (500ms pulse)
- **Safety:** Never assert both simultaneously
- **Interface:** 2x PC817 optocouplers for galvanic isolation

### Gate Node Inputs (from Apollo 635/636)
- **GPIO 25** ← Fully Open limit switch (via voltage divider or optocoupler)
- **GPIO 26** ← Fully Closed limit switch
- **Monitoring:** Every 10s during wake cycle
- **Detection:** State changes from ANY source (LoRa, RF remote, manual button)

### Power Supply Requirements
- **Input:** 12V from marine battery (shared with gate controller)
- **ESP32 Requirements:** 3.3V regulated (or 5V via USB)
- **Options:**
  - Buck converter (12V → 5V) + ESP32 onboard regulator
  - Buck converter (12V → 3.3V) direct to ESP32
- **Monitoring:** Battery voltage via ADC (<11.5V warning, <11.0V emergency mode)

---

## Current Challenge: Carrier Board Design

### Problem
No commercial carrier board exists with screw terminals specifically for Heltec LoRA32 boards.

### Requirements for Custom Carrier Board
1. **Screw terminals** for all GPIO connections
2. **Integrated power supply** (12V → 3.3V/5V buck converter)
3. **Optocoupler circuits** for gate control outputs (2x PC817)
4. **Input conditioning** for limit switch monitoring (voltage dividers or optocouplers)
5. **Battery voltage monitoring** circuit
6. **ESD protection** for outdoor installation
7. **Proper connector** for Heltec board mounting

### PCB Design Tool Selection

**Recommended: Flux.ai**
- AI-powered, browser-based PCB design tool
- Natural language interface for describing requirements
- Ideal for designers returning to PCB work after extended break
- Free 2-week trial, then $15-49/month
- Exports Gerbers, BOM, integrates with manufacturers

**Alternative: EasyEDA**
- Free, browser-based
- Drag-and-drop interface
- Direct JLCPCB integration
- Less AI assistance but very straightforward

**Alternative: Fritzing**
- Visual breadboard-style interface
- Good for simple breakout boards
- Auto-generates schematics and PCB from breadboard view

---

## Development Approach & Workflow

### Mode-Based Development Process

#### Planning Mode (Current)
- Brainstorm ideas and weigh design choices
- Create block diagrams and supporting documentation
- Ensure optimal path before software development
- Rigorous design decision documentation
- Informative mode for unfamiliar topics
- Minimal code generation (only basic examples/templates if needed)

#### Design Review Mode (Next)
- Investigate edge cases and failure modes
- Identify potential flaws and unforeseen consequences
- Evaluate tradeoffs
- Either return to planning or proceed to software development

#### Software Development Mode
- Code generation based on planning/design review
- Primary languages: C/C++, Python, ROS, shell
- Preferences:
  - Single inheritance designs
  - Clear class definitions and ownership
  - Unit tests only when prompted and classes finalized
  - Test scripts for manual testing
  - Python: UV and pyproject.toml for project management
  - Unit tests: pytest or gtest

#### Documentation Mode
- README.md files for basic repo information
- Sphinx-generated documentation for projects
- Google Docs for socializing changes/features

---

## Power Budget & Management

### Gate Node Strategy
- Deep sleep between status checks (~20 µA)
- Wake → read sensors → compare state → transmit if changed
- Battery voltage monitoring with alerts
- Emergency mode at <11.0V (prevents OPEN commands to ensure gate can close)

### Power Consumption Estimates
- **ESP32 Daily:** ~0.26 mAh (negligible vs. Apollo board's ~2-3 Ah/day)
- **Solar Charging:** Should maintain net positive balance

---

## Future Expansion (Planned)

### Timeline: Months to a year away
- Chicken coop monitoring nodes
- Well house monitoring nodes
- Cloud/internet connectivity for remote access
- Home Assistant integration
- MQTT cloud broker or VPN solution

### Scalability Considerations
- Message protocol designed for multi-node network
- MQTT architecture supports multiple devices
- Gateway can aggregate data from multiple LoRa nodes

---

## Security & Safety Features (To Be Implemented)

### Planned Security
- LoRa message encryption and authentication
- MQTT TLS, username/password
- Physical tamper detection
- Command injection prevention

### Safety Features
- Watchdog timer for ESP32
- Fallback to manual/RF control if LoRa fails
- Battery low-voltage protection
- Optocoupler isolation for gate controller interface

---

## Open Questions / Decisions Needed

1. **Gate Controller Clarification**
   - Exact model: Apollo 635/636 vs. GateCrafters GC-2000?
   - Voltage levels on OPEN/CLOSE terminals
   - Limit switch output characteristics

2. **Carrier Board Approach**
   - Custom PCB design vs. prototype board solution
   - Buck converter selection (12V → 5V vs. 12V → 3.3V)
   - Enclosure selection for outdoor deployment

3. **Environmental Protection**
   - Temperature range considerations
   - Weatherproof enclosure specifications
   - Mounting location relative to gate controller

4. **Timing Validation**
   - Is 10-second status update latency acceptable?
   - Command timeout and retry strategy details

---

## Next Steps (Recommended)

### Immediate (Planning Mode)
1. ✅ Validate LoRa communication with ping-pong test scripts
2. Create Interface Requirements Document (ICD)
3. Create detailed block diagram of carrier board
4. Finalize GPIO pin assignments
5. Select specific components (buck converter, optocouplers, connectors)

### Short-term (Design Review)
1. Review interface design for edge cases
2. Validate power budget calculations
3. Assess failure modes and mitigation strategies
4. Create Bill of Materials (BOM)

### Medium-term (Software Development)
1. Implement LoRa communication library
2. Develop state machine for gate control
3. Create MQTT interface code
4. Implement power management and deep sleep

### Long-term (Documentation & Testing)
1. Create Sphinx documentation
2. Develop comprehensive test suite
3. Field testing and validation
4. User documentation and deployment guide

---

## Resources & References

### Hardware Documentation
- Heltec ESP32 LoRa V3: https://docs.heltec.org/en/node/esp32/wifi_lora_32/index.html
- Heltec Arduino Library: https://github.com/HelTecAutomation/Heltec_ESP32
- Apollo Gate Controller: https://www.gatecrafters.com/product_detail_31215.aspx

### Development Tools
- Arduino IDE (for Heltec ESP32 development)
- Flux.ai (recommended for PCB design): https://www.flux.ai/p
- Alternative: EasyEDA: https://easyeda.com/

### LoRa Resources
- LoRa parameters optimized for 120 yard range
- SX1262 transceiver specifications
- 915MHz ISM band regulations (US)

---

## Notes for Claude Code (Linux Laptop)

### Development Environment Setup Needed
- Arduino IDE with Heltec ESP32 board definitions
- Heltec ESP32 library installed
- USB drivers for ESP32-S3 (Type-C interface)
- Git for version control

### Project Structure (To Be Created)
```
gate-monitor/
├── hardware/
│   ├── carrier-board/      # PCB design files
│   ├── schematics/          # Interface schematics
│   └── docs/                # Hardware documentation
├── firmware/
│   ├── gate-node/           # Gate ESP32 code
│   ├── house-gateway/       # Gateway ESP32 code
│   └── common/              # Shared libraries
├── backend/
│   ├── mqtt-broker/         # Mosquitto config
│   └── web-server/          # User interface
├── docs/                    # Sphinx documentation
└── tests/                   # Test scripts
```

### Initial Tasks for Claude Code
1. Set up Arduino project structure for Heltec ESP32
2. Create ping-pong communication test script
3. Implement basic LoRa send/receive functions
4. Create test harness for manual hardware validation

---

## Project Philosophy

This project balances practical automation needs with learning objectives:
- **Methodical approach:** Validate hardware before complex implementation
- **Proper planning:** Document requirements before coding
- **Component selection:** Research options, verify compatibility
- **Future-proof design:** Build foundation for expansion
- **Reliability focus:** Outdoor installation requires robust design

---

**End of Context Summary**

*This document should provide Claude Code with complete project context for Linux-based firmware development, testing, and documentation tasks.*
