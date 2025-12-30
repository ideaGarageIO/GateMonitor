/*
 * Gate Node - LoRa Gate Monitor & Control
 * Heltec WiFi LoRa 32 V3
 *
 * Monitors gate limit switches and controls gate via optocouplers.
 * Radio always listening for commands from gateway.
 * Sends heartbeat every 10 seconds.
 * Display turns off after 30s boot period + confirmed connection.
 */

#include "LoRaWan_APP.h"
#include "Arduino.h"
#include <Wire.h>
#include "HT_SSD1306Wire.h"
#include "gate_protocol.h"

// Display
static SSD1306Wire display(0x3c, 500000, SDA_OLED, SCL_OLED, GEOMETRY_128_64, RST_OLED);

// GPIO Pin Assignments
#define PIN_LIMIT_OPEN    5     // Limit switch: fully open
#define PIN_LIMIT_CLOSED  6     // Limit switch: fully closed
#define PIN_CTRL_OPEN     7     // Optocoupler: open command
#define PIN_CTRL_CLOSE    8     // Optocoupler: close command
#define PIN_BATTERY_ADC   1     // Battery voltage divider

// Timing Configuration
#define HEARTBEAT_INTERVAL_MS   10000   // Heartbeat every 10 seconds
#define DISPLAY_TIMEOUT_MS      30000   // Display on for 30 seconds at boot
#define CONTROL_PULSE_MS        500     // Pulse duration for gate command
#define STATE_CHECK_INTERVAL_MS 1000    // Check gate state every 1 second
#define REQUIRED_ACKS           3       // ACKs needed to confirm connection

// Mock gate configuration
#define MOCK_GATE_ENABLED       true    // Set to false to use real sensors
#define MOCK_TRANSITION_MS      15000   // Time to transition between states (15 seconds)

// State variables
static uint8_t currentState = STATE_UNKNOWN;
static uint8_t lastState = STATE_UNKNOWN;
static uint16_t batteryMv = 0;
static uint16_t sequenceNum = 0;

// Mock gate state machine
static uint8_t mockTargetState = STATE_CLOSED;  // Where gate is heading
static unsigned long mockTransitionStart = 0;   // When transition started
static bool mockInTransition = false;           // Currently moving?

// Timing
static unsigned long lastHeartbeat = 0;
static unsigned long lastStateCheck = 0;
static unsigned long bootTime = 0;

// Connection tracking
static uint8_t ackCount = 0;
static bool connectionConfirmed = false;
static unsigned long lastAckTime = 0;

// Display state
static bool displayEnabled = true;
static bool displayCanTurnOff = false;

// Command display state
static const char* lastCommand = nullptr;
static unsigned long lastCommandTime = 0;
#define COMMAND_DISPLAY_DURATION_MS  5000  // Show command for 5 seconds

// LoRa state
static bool lora_idle = true;
static uint16_t pendingAckSeq = 0;

// LoRa buffers
char txpacket[BUFFER_SIZE];
char rxpacket[BUFFER_SIZE];
static RadioEvents_t RadioEvents;

// Function declarations
void VextON();
void VextOFF();
void initDisplay();
void initLoRa();
void initGPIO();
uint8_t readGateState();
uint16_t readBatteryVoltage();
void sendHeartbeat();
void sendStatus();
void processCommand(uint8_t cmd);
void pulseOutput(uint8_t pin);
void updateDisplay();
void checkDisplayTimeout();
void turnOffDisplay();
void turnOnDisplay();
void showCommandReceived(const char* cmdName);
void mockGateCommand(uint8_t cmd);
void updateMockGate();
void OnTxDone();
void OnTxTimeout();
void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr);

void VextON() {
    pinMode(Vext, OUTPUT);
    digitalWrite(Vext, LOW);
}

void VextOFF() {
    pinMode(Vext, OUTPUT);
    digitalWrite(Vext, HIGH);
}

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n=============================");
    Serial.println("   GATE NODE - Starting Up");
    Serial.println("=============================");

    bootTime = millis();

    // Initialize hardware
    VextON();
    delay(100);

    initDisplay();
    initGPIO();

    // Show boot message
    display.clear();
    display.setFont(ArialMT_Plain_16);
    display.drawString(0, 0, "GATE NODE");
    display.setFont(ArialMT_Plain_10);
    display.drawString(0, 20, "Initializing...");
    display.display();

    initLoRa();

    // Read initial state
    if (MOCK_GATE_ENABLED) {
        // Mock mode: start as CLOSED
        currentState = STATE_CLOSED;
        mockTargetState = STATE_CLOSED;
        mockInTransition = false;
        Serial.println("*** MOCK GATE MODE ENABLED ***");
    } else {
        currentState = readGateState();
    }
    lastState = currentState;
    batteryMv = readBatteryVoltage();

    Serial.printf("Initial State: %s\n", stateToString(currentState));
    Serial.printf("Battery: %u mV (%.2fV)\n", batteryMv, batteryMv / 1000.0);

    // Send initial status
    sendStatus();

    Serial.println("Gate Node Ready - Listening for commands");
    Serial.println("Display will turn off after 30s + connection confirmed");
}

void loop() {
    unsigned long now = millis();

    // Process radio events (always - for receiving commands)
    Radio.IrqProcess();

    // Update mock gate state machine (if enabled)
    if (MOCK_GATE_ENABLED) {
        updateMockGate();
    }

    // Periodic state check
    if (now - lastStateCheck >= STATE_CHECK_INTERVAL_MS) {
        lastStateCheck = now;

        uint8_t newState;
        if (MOCK_GATE_ENABLED) {
            newState = currentState;  // Mock state is updated by updateMockGate()
        } else {
            newState = readGateState();
        }

        if (newState != lastState) {
            Serial.printf("State changed: %s -> %s\n",
                stateToString(lastState), stateToString(newState));
            lastState = newState;
            sendStatus();  // Send immediately on state change
        }
    }

    // Periodic heartbeat
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL_MS) {
        batteryMv = readBatteryVoltage();
        sendHeartbeat();
        lastHeartbeat = now;
    }

    // Check if display should turn off
    checkDisplayTimeout();

    // Update display if enabled
    if (displayEnabled) {
        updateDisplay();
    }

    // Small delay to reduce CPU usage
    delay(10);
}

void initDisplay() {
    display.init();
    display.clear();
    display.setContrast(255);
    display.setTextAlignment(TEXT_ALIGN_LEFT);
    displayEnabled = true;
    Serial.println("Display initialized");
}

void initLoRa() {
    RadioEvents.TxDone = OnTxDone;
    RadioEvents.TxTimeout = OnTxTimeout;
    RadioEvents.RxDone = OnRxDone;

    Mcu.begin(HELTEC_BOARD, SLOW_CLK_TPYE);
    Radio.Init(&RadioEvents);
    Radio.SetChannel(RF_FREQUENCY);

    Radio.SetTxConfig(
        MODEM_LORA, TX_OUTPUT_POWER, 0, LORA_BANDWIDTH,
        LORA_SPREADING_FACTOR, LORA_CODINGRATE,
        LORA_PREAMBLE_LENGTH, LORA_FIX_LENGTH_PAYLOAD_ON,
        true, 0, 0, LORA_IQ_INVERSION_ON, 3000
    );

    Radio.SetRxConfig(
        MODEM_LORA, LORA_BANDWIDTH, LORA_SPREADING_FACTOR,
        LORA_CODINGRATE, 0, LORA_PREAMBLE_LENGTH,
        LORA_SYMBOL_TIMEOUT, LORA_FIX_LENGTH_PAYLOAD_ON,
        0, true, 0, 0, LORA_IQ_INVERSION_ON, true
    );

    // Start in continuous RX mode - always listening
    Radio.Rx(0);
    lora_idle = true;

    Serial.println("LoRa initialized - Continuous RX mode");
}

void initGPIO() {
    // Limit switch inputs (active LOW with internal pullup)
    pinMode(PIN_LIMIT_OPEN, INPUT_PULLUP);
    pinMode(PIN_LIMIT_CLOSED, INPUT_PULLUP);

    // Control outputs (active HIGH to trigger optocoupler)
    pinMode(PIN_CTRL_OPEN, OUTPUT);
    pinMode(PIN_CTRL_CLOSE, OUTPUT);
    digitalWrite(PIN_CTRL_OPEN, LOW);
    digitalWrite(PIN_CTRL_CLOSE, LOW);

    Serial.println("GPIO initialized");
}

uint8_t readGateState() {
    bool openSwitch = !digitalRead(PIN_LIMIT_OPEN);    // Active LOW
    bool closedSwitch = !digitalRead(PIN_LIMIT_CLOSED);

    if (closedSwitch && !openSwitch) {
        return STATE_CLOSED;
    } else if (openSwitch && !closedSwitch) {
        return STATE_OPEN;
    } else if (!openSwitch && !closedSwitch) {
        return STATE_MOVING;
    } else {
        return STATE_ERROR;
    }
}

uint16_t readBatteryVoltage() {
    const float DIVIDER_RATIO = 4.03;
    const float ADC_REF = 3300.0;
    const int ADC_MAX = 4095;

    // Average multiple readings
    int total = 0;
    for (int i = 0; i < 4; i++) {
        total += analogRead(PIN_BATTERY_ADC);
        delay(2);
    }
    int adcValue = total / 4;

    float voltage = (adcValue * ADC_REF / ADC_MAX) * DIVIDER_RATIO;
    return (uint16_t)voltage;
}

void sendHeartbeat() {
    sequenceNum++;
    formatHeartbeatMessage(txpacket, currentState, batteryMv, sequenceNum);

    Serial.printf("TX Heartbeat [%u]: %s\n", sequenceNum, txpacket);

    pendingAckSeq = sequenceNum;
    lora_idle = false;
    Radio.Send((uint8_t *)txpacket, strlen(txpacket));
}

void sendStatus() {
    sequenceNum++;
    formatStatusMessage(txpacket, currentState, batteryMv, sequenceNum);

    Serial.printf("TX Status [%u]: %s\n", sequenceNum, txpacket);

    pendingAckSeq = sequenceNum;
    lora_idle = false;
    Radio.Send((uint8_t *)txpacket, strlen(txpacket));
}

void processCommand(uint8_t cmd) {
    const char* cmdName = commandToString(cmd);
    Serial.printf("Executing command: %s\n", cmdName);

    // Show command on display for debugging
    showCommandReceived(cmdName);

    // Safety: don't open if battery critically low
    if (cmd == CMD_OPEN && batteryMv < BATTERY_CRITICAL) {
        Serial.println("BLOCKED: Battery critical - cannot open gate");
        return;
    }

    // Use mock or real gate control
    if (MOCK_GATE_ENABLED) {
        mockGateCommand(cmd);
    } else {
        switch (cmd) {
            case CMD_OPEN:
                Serial.println("Opening gate...");
                pulseOutput(PIN_CTRL_OPEN);
                break;
            case CMD_CLOSE:
                Serial.println("Closing gate...");
                pulseOutput(PIN_CTRL_CLOSE);
                break;
            case CMD_STOP:
                Serial.println("Stopping gate...");
                pulseOutput(PIN_CTRL_OPEN);  // Most controllers: any pulse = stop if moving
                break;
            case CMD_STATUS:
                Serial.println("Status requested");
                sendStatus();
                break;
        }
    }
}

void pulseOutput(uint8_t pin) {
    digitalWrite(pin, HIGH);
    delay(CONTROL_PULSE_MS);
    digitalWrite(pin, LOW);
}

void mockGateCommand(uint8_t cmd) {
    switch (cmd) {
        case CMD_OPEN:
            if (currentState != STATE_OPEN) {
                Serial.println("[MOCK] Starting OPEN transition...");
                mockTargetState = STATE_OPEN;
                mockInTransition = true;
                mockTransitionStart = millis();
                currentState = STATE_MOVING;
                sendStatus();
            } else {
                Serial.println("[MOCK] Gate already OPEN");
            }
            break;

        case CMD_CLOSE:
            if (currentState != STATE_CLOSED) {
                Serial.println("[MOCK] Starting CLOSE transition...");
                mockTargetState = STATE_CLOSED;
                mockInTransition = true;
                mockTransitionStart = millis();
                currentState = STATE_MOVING;
                sendStatus();
            } else {
                Serial.println("[MOCK] Gate already CLOSED");
            }
            break;

        case CMD_STOP:
            if (mockInTransition) {
                Serial.println("[MOCK] STOP - halting in MOVING state");
                mockInTransition = false;
                // Stay in MOVING state (simulates gate stopped mid-travel)
            } else {
                Serial.println("[MOCK] Gate not moving, STOP ignored");
            }
            break;

        case CMD_STATUS:
            Serial.println("[MOCK] Status requested");
            sendStatus();
            break;
    }
}

void updateMockGate() {
    if (!mockInTransition) return;

    unsigned long elapsed = millis() - mockTransitionStart;

    if (elapsed >= MOCK_TRANSITION_MS) {
        // Transition complete
        currentState = mockTargetState;
        mockInTransition = false;

        Serial.printf("[MOCK] Transition complete -> %s\n", stateToString(currentState));
        sendStatus();
    }
}

void checkDisplayTimeout() {
    if (!displayEnabled) return;

    unsigned long now = millis();
    unsigned long uptime = now - bootTime;
    bool timeoutReached = (uptime >= DISPLAY_TIMEOUT_MS);

    // If showing a command, wait for command display duration
    if (lastCommand != nullptr) {
        if (now - lastCommandTime >= COMMAND_DISPLAY_DURATION_MS) {
            Serial.println("Command display duration ended");
            lastCommand = nullptr;
            // Re-enable display timeout after command shown
            if (connectionConfirmed && timeoutReached) {
                displayCanTurnOff = true;
            }
        }
        return;  // Don't turn off while showing command
    }

    // Can turn off if: 30 seconds passed AND connection confirmed
    if (timeoutReached && connectionConfirmed && !displayCanTurnOff) {
        displayCanTurnOff = true;
        Serial.println("Display timeout reached and connection confirmed");
        Serial.printf("  - Uptime: %lu ms\n", uptime);
        Serial.printf("  - ACKs received: %d\n", ackCount);
    }

    if (displayCanTurnOff) {
        turnOffDisplay();
    }
}

void turnOffDisplay() {
    if (!displayEnabled) return;

    Serial.println("Turning off display to save power");

    display.clear();
    display.setFont(ArialMT_Plain_10);
    display.drawString(0, 24, "Display OFF");
    display.drawString(0, 36, "Radio listening...");
    display.display();
    delay(1000);

    display.displayOff();
    VextOFF();
    displayEnabled = false;

    Serial.println("Display disabled - power saving mode active");
}

void turnOnDisplay() {
    if (displayEnabled) return;

    Serial.println("Turning on display for command feedback");

    VextON();
    delay(50);

    display.displayOn();
    display.init();
    display.clear();
    display.setContrast(255);
    display.setTextAlignment(TEXT_ALIGN_LEFT);
    displayEnabled = true;

    // Reset the timeout - allow display to turn off after command is processed
    displayCanTurnOff = false;
}

void showCommandReceived(const char* cmdName) {
    // Turn on display if it was off
    turnOnDisplay();

    // Store command for display
    lastCommand = cmdName;
    lastCommandTime = millis();

    // Show command immediately
    display.clear();

    display.setFont(ArialMT_Plain_16);
    display.drawString(0, 0, "COMMAND RX");

    display.setFont(ArialMT_Plain_24);
    display.drawStringMaxWidth(0, 22, 128, cmdName);

    display.setFont(ArialMT_Plain_10);
    display.drawString(0, 54, "Processing...");

    display.display();

    Serial.printf("Display showing command: %s\n", cmdName);
}

void updateDisplay() {
    static unsigned long lastDisplayUpdate = 0;

    // Update display every 250ms to avoid flicker
    if (millis() - lastDisplayUpdate < 250) return;
    lastDisplayUpdate = millis();

    // If showing a command, display command screen instead of normal status
    if (lastCommand != nullptr) {
        display.clear();

        display.setFont(ArialMT_Plain_16);
        display.drawString(0, 0, "COMMAND RX");

        display.setFont(ArialMT_Plain_24);
        display.drawStringMaxWidth(0, 22, 128, lastCommand);

        // Show remaining time
        unsigned long elapsed = millis() - lastCommandTime;
        int remaining = (COMMAND_DISPLAY_DURATION_MS - elapsed) / 1000;
        display.setFont(ArialMT_Plain_10);
        char buf[32];
        sprintf(buf, "Executed (%ds)", remaining > 0 ? remaining : 0);
        display.drawString(0, 54, buf);

        display.display();
        return;
    }

    display.clear();

    // Header
    display.setFont(ArialMT_Plain_16);
    if (MOCK_GATE_ENABLED) {
        display.drawString(0, 0, "GATE [MOCK]");
    } else {
        display.drawString(0, 0, "GATE NODE");
    }

    display.setFont(ArialMT_Plain_10);

    // Gate State with mock transition info
    String stateStr = "State: ";
    stateStr += stateToString(currentState);
    if (MOCK_GATE_ENABLED && mockInTransition) {
        unsigned long elapsed = millis() - mockTransitionStart;
        int remaining = (MOCK_TRANSITION_MS - elapsed) / 1000;
        stateStr += " (" + String(remaining) + "s)";
    }
    display.drawString(0, 18, stateStr);

    // Battery voltage with status
    char battStr[32];
    sprintf(battStr, "Battery: %.2fV", batteryMv / 1000.0);
    display.drawString(0, 30, battStr);

    // Battery warning
    if (batteryMv < BATTERY_CRITICAL) {
        display.drawString(90, 30, "CRIT!");
    } else if (batteryMv < BATTERY_LOW) {
        display.drawString(90, 30, "LOW");
    }

    // Connection status
    String connStr = "Link: ";
    if (connectionConfirmed) {
        connStr += "OK (" + String(ackCount) + " ACKs)";
    } else {
        connStr += "Waiting... (" + String(ackCount) + "/" + String(REQUIRED_ACKS) + ")";
    }
    display.drawString(0, 42, connStr);

    // Countdown to display off
    unsigned long uptime = millis() - bootTime;
    if (uptime < DISPLAY_TIMEOUT_MS) {
        int remaining = (DISPLAY_TIMEOUT_MS - uptime) / 1000;
        String countStr = "Display off in: " + String(remaining) + "s";
        display.drawString(0, 54, countStr);
    } else if (!connectionConfirmed) {
        display.drawString(0, 54, "Waiting for connection...");
    } else {
        display.drawString(0, 54, "Ready to sleep");
    }

    display.display();
}

// LoRa Callbacks
void OnTxDone() {
    Serial.println("TX Complete");
    lora_idle = true;
    Radio.Rx(0);  // Return to RX mode immediately
}

void OnTxTimeout() {
    Serial.println("TX Timeout!");
    lora_idle = true;
    Radio.Rx(0);  // Return to RX mode
}

void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr) {
    memcpy(rxpacket, payload, size);
    rxpacket[size] = '\0';

    Serial.printf("RX [RSSI:%d SNR:%d]: %s\n", rssi, snr, rxpacket);

    char msgType = rxpacket[0];

    if (msgType == MSG_ACK) {
        // ACK received
        uint16_t ackSeq = 0;
        if (sscanf(rxpacket, "A|%hu", &ackSeq) == 1) {
            Serial.printf("ACK for seq %u (expected %u)\n", ackSeq, pendingAckSeq);

            if (ackSeq == pendingAckSeq) {
                ackCount++;
                lastAckTime = millis();
                pendingAckSeq = 0;

                Serial.printf("ACK confirmed! Total ACKs: %d\n", ackCount);

                // Check if connection is now confirmed
                if (!connectionConfirmed && ackCount >= REQUIRED_ACKS) {
                    connectionConfirmed = true;
                    Serial.println("*** CONNECTION CONFIRMED ***");
                }
            }
        }
    } else if (msgType == MSG_COMMAND) {
        // Command received
        uint8_t cmd = 0;
        uint16_t seq = 0;
        if (sscanf(rxpacket, "C|%hhu|%hu", &cmd, &seq) == 2) {
            Serial.printf("Command received: %s (seq %u)\n", commandToString(cmd), seq);

            // Send ACK first
            char ackBuf[16];
            formatAckMessage(ackBuf, seq);
            Serial.printf("TX ACK: %s\n", ackBuf);
            Radio.Send((uint8_t *)ackBuf, strlen(ackBuf));

            // Process the command after ACK is queued
            processCommand(cmd);
        }
    }

    lora_idle = true;
}
