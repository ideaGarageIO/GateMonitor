/*
 * Gate Node - LoRa Gate Monitor & Control
 * Heltec WiFi LoRa 32 V3
 *
 * Monitors gate limit switches and controls gate via optocouplers.
 * Communicates with house gateway over LoRa.
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

// Control timing
#define CONTROL_PULSE_MS  500   // Pulse duration for gate command

// State variables
static uint8_t currentState = STATE_UNKNOWN;
static uint8_t lastState = STATE_UNKNOWN;
static uint16_t batteryMv = 0;
static uint16_t sequenceNum = 0;
static unsigned long lastHeartbeat = 0;
static unsigned long lastStateChange = 0;

// LoRa buffers
char txpacket[BUFFER_SIZE];
char rxpacket[BUFFER_SIZE];
static RadioEvents_t RadioEvents;
bool lora_idle = true;

// Pending ACK tracking
static uint16_t pendingAckSeq = 0;
static unsigned long pendingAckTime = 0;
static uint8_t retryCount = 0;

// Function declarations
void VextON();
void VextOFF();
void initDisplay();
void initLoRa();
void initGPIO();
uint8_t readGateState();
uint16_t readBatteryVoltage();
void sendStatus();
void sendHeartbeat();
void processCommand(uint8_t cmd);
void pulseOutput(uint8_t pin);
void updateDisplay();
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
    delay(1000);

    Serial.println("=== Gate Node Starting ===");

    VextON();
    delay(100);

    initDisplay();
    initGPIO();
    initLoRa();

    // Read initial state
    currentState = readGateState();
    lastState = currentState;
    batteryMv = readBatteryVoltage();

    // Send initial status
    sendStatus();

    Serial.println("Gate Node Ready");
    Serial.printf("Initial State: %s\n", stateToString(currentState));
    Serial.printf("Battery: %u mV\n", batteryMv);
}

void loop() {
    unsigned long now = millis();

    // Read current gate state
    currentState = readGateState();

    // State change detection
    if (currentState != lastState) {
        if (now - lastStateChange > DEBOUNCE_TIME) {
            Serial.printf("State changed: %s -> %s\n",
                stateToString(lastState), stateToString(currentState));
            lastState = currentState;
            lastStateChange = now;
            sendStatus();
        }
    }

    // Periodic heartbeat
    if (now - lastHeartbeat >= HEARTBEAT_INTERVAL) {
        batteryMv = readBatteryVoltage();
        sendHeartbeat();
        lastHeartbeat = now;
    }

    // ACK timeout / retry
    if (pendingAckSeq > 0 && (now - pendingAckTime >= ACK_TIMEOUT)) {
        if (retryCount < RETRY_COUNT) {
            Serial.printf("ACK timeout, retry %d\n", retryCount + 1);
            // Resend last message
            if (lora_idle) {
                Radio.Send((uint8_t *)txpacket, strlen(txpacket));
                lora_idle = false;
                pendingAckTime = now;
                retryCount++;
            }
        } else {
            Serial.println("ACK failed after retries");
            pendingAckSeq = 0;
            retryCount = 0;
        }
    }

    // Update display
    updateDisplay();

    // Process radio events
    Radio.IrqProcess();
}

void initDisplay() {
    display.init();
    display.clear();
    display.setContrast(255);
    display.setTextAlignment(TEXT_ALIGN_LEFT);
    display.setFont(ArialMT_Plain_10);
    display.drawString(0, 0, "Gate Node");
    display.drawString(0, 12, "Initializing...");
    display.display();
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

    Radio.Rx(0);
    Serial.println("LoRa initialized");
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
        // Both switches active = error condition
        return STATE_ERROR;
    }
}

uint16_t readBatteryVoltage() {
    // Read ADC and convert to millivolts
    // Assuming voltage divider: 12V -> 3.3V range
    // Divider ratio depends on resistor values
    // Example: 10k/3.3k divider = 4.03 ratio
    const float DIVIDER_RATIO = 4.03;
    const float ADC_REF = 3300.0;  // 3.3V reference in mV
    const int ADC_MAX = 4095;       // 12-bit ADC

    int adcValue = analogRead(PIN_BATTERY_ADC);
    float voltage = (adcValue * ADC_REF / ADC_MAX) * DIVIDER_RATIO;

    return (uint16_t)voltage;
}

void sendStatus() {
    sequenceNum++;
    formatStatusMessage(txpacket, currentState, batteryMv, sequenceNum);

    Serial.printf("TX Status: %s\n", txpacket);

    if (lora_idle) {
        lora_idle = false;
        pendingAckSeq = sequenceNum;
        pendingAckTime = millis();
        retryCount = 0;
        Radio.Send((uint8_t *)txpacket, strlen(txpacket));
    }
}

void sendHeartbeat() {
    sequenceNum++;
    formatHeartbeatMessage(txpacket, currentState, batteryMv, sequenceNum);

    Serial.printf("TX Heartbeat: %s\n", txpacket);

    if (lora_idle) {
        lora_idle = false;
        pendingAckSeq = sequenceNum;
        pendingAckTime = millis();
        retryCount = 0;
        Radio.Send((uint8_t *)txpacket, strlen(txpacket));
    }
}

void processCommand(uint8_t cmd) {
    Serial.printf("Processing command: %s\n", commandToString(cmd));

    // Safety check: don't open if battery critically low
    if (cmd == CMD_OPEN && batteryMv < BATTERY_CRITICAL) {
        Serial.println("Battery critical - OPEN command blocked");
        return;
    }

    switch (cmd) {
        case CMD_OPEN:
            pulseOutput(PIN_CTRL_OPEN);
            break;
        case CMD_CLOSE:
            pulseOutput(PIN_CTRL_CLOSE);
            break;
        case CMD_STOP:
            // Pulse either to stop (depends on controller)
            pulseOutput(PIN_CTRL_OPEN);
            break;
        case CMD_STATUS:
            sendStatus();
            break;
    }
}

void pulseOutput(uint8_t pin) {
    digitalWrite(pin, HIGH);
    delay(CONTROL_PULSE_MS);
    digitalWrite(pin, LOW);
}

void updateDisplay() {
    display.clear();
    display.setFont(ArialMT_Plain_10);

    // Header
    display.drawString(0, 0, "GATE NODE");
    display.drawLine(0, 11, 128, 11);

    // State
    display.drawString(0, 14, "State: " + String(stateToString(currentState)));

    // Battery
    char battStr[20];
    sprintf(battStr, "Batt: %.2fV", batteryMv / 1000.0);
    display.drawString(0, 26, battStr);

    // Battery status indicator
    if (batteryMv < BATTERY_CRITICAL) {
        display.drawString(80, 26, "CRIT!");
    } else if (batteryMv < BATTERY_LOW) {
        display.drawString(80, 26, "LOW");
    }

    // Sequence
    display.drawString(0, 38, "Seq: " + String(sequenceNum));

    // Pending ACK
    if (pendingAckSeq > 0) {
        display.drawString(0, 50, "Waiting ACK...");
    } else {
        display.drawString(0, 50, "Idle");
    }

    display.display();
}

// LoRa Callbacks
void OnTxDone() {
    Serial.println("TX Done");
    lora_idle = true;
    Radio.Rx(0);
}

void OnTxTimeout() {
    Serial.println("TX Timeout");
    lora_idle = true;
    Radio.Rx(0);
}

void OnRxDone(uint8_t *payload, uint16_t size, int16_t rssi, int8_t snr) {
    memcpy(rxpacket, payload, size);
    rxpacket[size] = '\0';

    Serial.printf("RX: %s (RSSI: %d, SNR: %d)\n", rxpacket, rssi, snr);

    // Parse message
    char msgType = rxpacket[0];

    if (msgType == MSG_ACK) {
        // Parse ACK sequence
        uint16_t ackSeq = 0;
        if (sscanf(rxpacket, "A|%hu", &ackSeq) == 1) {
            if (ackSeq == pendingAckSeq) {
                Serial.println("ACK received");
                pendingAckSeq = 0;
                retryCount = 0;
            }
        }
    } else if (msgType == MSG_COMMAND) {
        // Parse command
        uint8_t cmd = 0;
        uint16_t seq = 0;
        if (sscanf(rxpacket, "C|%hhu|%hu", &cmd, &seq) == 2) {
            // Send ACK
            char ackBuf[16];
            formatAckMessage(ackBuf, seq);
            if (lora_idle) {
                lora_idle = false;
                Radio.Send((uint8_t *)ackBuf, strlen(ackBuf));
            }

            // Process command
            processCommand(cmd);
        }
    }

    lora_idle = true;
}
