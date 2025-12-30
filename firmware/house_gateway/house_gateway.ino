/*
 * House Gateway - LoRa to WiFi/MQTT Bridge
 * Heltec WiFi LoRa 32 V3
 *
 * Receives gate status over LoRa and publishes to MQTT.
 * Receives MQTT commands and forwards to gate over LoRa.
 */

#include "LoRaWan_APP.h"
#include "Arduino.h"
#include <Wire.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "HT_SSD1306Wire.h"
#include "gate_protocol.h"

// Display
static SSD1306Wire display(0x3c, 500000, SDA_OLED, SCL_OLED, GEOMETRY_128_64, RST_OLED);

// WiFi Configuration - UPDATE THESE
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// MQTT Configuration
const char* MQTT_SERVER = "192.168.1.100";  // Raspberry Pi IP
const int MQTT_PORT = 1883;
const char* MQTT_USER = "";                  // Optional
const char* MQTT_PASSWORD = "";              // Optional
const char* MQTT_CLIENT_ID = "gate_gateway";

// MQTT Topics
const char* TOPIC_STATUS = "gate/status";
const char* TOPIC_COMMAND = "gate/command";
const char* TOPIC_BATTERY = "gate/battery";
const char* TOPIC_RSSI = "gate/rssi";
const char* TOPIC_ONLINE = "gate/online";

// WiFi and MQTT clients
WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// State
static uint8_t gateState = STATE_UNKNOWN;
static uint16_t gateBattery = 0;
static int16_t lastRssi = 0;
static int8_t lastSnr = 0;
static uint16_t commandSeq = 0;
static unsigned long lastGateMessage = 0;
static bool gateOnline = false;

// LoRa buffers
char txpacket[BUFFER_SIZE];
char rxpacket[BUFFER_SIZE];
static RadioEvents_t RadioEvents;
bool lora_idle = true;

// Pending command
static uint8_t pendingCmd = 0;
static uint16_t pendingCmdSeq = 0;
static unsigned long pendingCmdTime = 0;
static uint8_t cmdRetryCount = 0;

// Function declarations
void VextON();
void VextOFF();
void initDisplay();
void initLoRa();
void initWiFi();
void initMQTT();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void reconnectMQTT();
void sendCommand(uint8_t cmd);
void publishStatus();
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

    Serial.println("=== House Gateway Starting ===");

    VextON();
    delay(100);

    initDisplay();
    initLoRa();
    initWiFi();
    initMQTT();

    Serial.println("House Gateway Ready");
}

void loop() {
    unsigned long now = millis();

    // Maintain WiFi connection
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi disconnected, reconnecting...");
        initWiFi();
    }

    // Maintain MQTT connection
    if (!mqtt.connected()) {
        reconnectMQTT();
    }
    mqtt.loop();

    // Check gate online status (offline if no message for 2x heartbeat interval)
    if (gateOnline && (now - lastGateMessage > HEARTBEAT_INTERVAL * 2)) {
        gateOnline = false;
        mqtt.publish(TOPIC_ONLINE, "offline", true);
        Serial.println("Gate went offline");
    }

    // Command retry
    if (pendingCmdSeq > 0 && (now - pendingCmdTime >= ACK_TIMEOUT)) {
        if (cmdRetryCount < RETRY_COUNT) {
            Serial.printf("Command ACK timeout, retry %d\n", cmdRetryCount + 1);
            if (lora_idle) {
                formatCommandMessage(txpacket, pendingCmd, pendingCmdSeq);
                Radio.Send((uint8_t *)txpacket, strlen(txpacket));
                lora_idle = false;
                pendingCmdTime = now;
                cmdRetryCount++;
            }
        } else {
            Serial.println("Command failed after retries");
            pendingCmdSeq = 0;
            cmdRetryCount = 0;
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
    display.drawString(0, 0, "House Gateway");
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

void initWiFi() {
    Serial.printf("Connecting to WiFi: %s\n", WIFI_SSID);

    display.clear();
    display.drawString(0, 0, "Connecting WiFi...");
    display.display();

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println();
        Serial.printf("WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\nWiFi connection failed!");
    }
}

void initMQTT() {
    mqtt.setServer(MQTT_SERVER, MQTT_PORT);
    mqtt.setCallback(mqttCallback);
    reconnectMQTT();
}

void reconnectMQTT() {
    int attempts = 0;
    while (!mqtt.connected() && attempts < 5) {
        Serial.println("Connecting to MQTT...");

        if (mqtt.connect(MQTT_CLIENT_ID, MQTT_USER, MQTT_PASSWORD)) {
            Serial.println("MQTT connected");

            // Subscribe to command topic
            mqtt.subscribe(TOPIC_COMMAND);

            // Publish gateway online
            mqtt.publish("gateway/online", "online", true);
        } else {
            Serial.printf("MQTT failed, rc=%d\n", mqtt.state());
            delay(2000);
        }
        attempts++;
    }
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
    char message[64];
    int len = min((unsigned int)63, length);
    memcpy(message, payload, len);
    message[len] = '\0';

    Serial.printf("MQTT RX [%s]: %s\n", topic, message);

    if (strcmp(topic, TOPIC_COMMAND) == 0) {
        uint8_t cmd = 0;

        if (strcasecmp(message, "OPEN") == 0) {
            cmd = CMD_OPEN;
        } else if (strcasecmp(message, "CLOSE") == 0) {
            cmd = CMD_CLOSE;
        } else if (strcasecmp(message, "STOP") == 0) {
            cmd = CMD_STOP;
        } else if (strcasecmp(message, "STATUS") == 0) {
            cmd = CMD_STATUS;
        }

        if (cmd > 0) {
            sendCommand(cmd);
        }
    }
}

void sendCommand(uint8_t cmd) {
    commandSeq++;
    pendingCmd = cmd;
    pendingCmdSeq = commandSeq;
    pendingCmdTime = millis();
    cmdRetryCount = 0;

    formatCommandMessage(txpacket, cmd, commandSeq);
    Serial.printf("TX Command: %s\n", txpacket);

    if (lora_idle) {
        lora_idle = false;
        Radio.Send((uint8_t *)txpacket, strlen(txpacket));
    }
}

void publishStatus() {
    // Publish JSON status
    char json[128];
    sprintf(json, "{\"state\":\"%s\",\"battery\":%u,\"rssi\":%d,\"snr\":%d,\"online\":true}",
        stateToString(gateState), gateBattery, lastRssi, lastSnr);

    mqtt.publish(TOPIC_STATUS, json, true);

    // Publish individual values
    char buf[16];
    sprintf(buf, "%u", gateBattery);
    mqtt.publish(TOPIC_BATTERY, buf, true);

    sprintf(buf, "%d", lastRssi);
    mqtt.publish(TOPIC_RSSI, buf, true);
}

void updateDisplay() {
    display.clear();
    display.setFont(ArialMT_Plain_10);

    // Header with WiFi status
    String header = "GATEWAY ";
    header += WiFi.status() == WL_CONNECTED ? "W" : "-";
    header += mqtt.connected() ? "M" : "-";
    display.drawString(0, 0, header);
    display.drawLine(0, 11, 128, 11);

    // Gate state
    display.drawString(0, 14, "Gate: " + String(stateToString(gateState)));

    // Online status
    display.drawString(70, 14, gateOnline ? "[ON]" : "[OFF]");

    // Battery
    char battStr[20];
    sprintf(battStr, "Batt: %.2fV", gateBattery / 1000.0);
    display.drawString(0, 26, battStr);

    // Signal quality
    char sigStr[24];
    sprintf(sigStr, "RSSI:%d SNR:%d", lastRssi, lastSnr);
    display.drawString(0, 38, sigStr);

    // IP address
    if (WiFi.status() == WL_CONNECTED) {
        display.drawString(0, 50, WiFi.localIP().toString());
    } else {
        display.drawString(0, 50, "WiFi disconnected");
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

    lastRssi = rssi;
    lastSnr = snr;

    Serial.printf("RX: %s (RSSI: %d, SNR: %d)\n", rxpacket, rssi, snr);

    char msgType = rxpacket[0];

    if (msgType == MSG_STATUS || msgType == MSG_HEARTBEAT) {
        // Parse status/heartbeat: S|<state>|<battery>|<seq>
        uint8_t state = 0;
        uint16_t battery = 0;
        uint16_t seq = 0;

        if (sscanf(rxpacket + 2, "%hhu|%hu|%hu", &state, &battery, &seq) == 3) {
            gateState = state;
            gateBattery = battery;
            lastGateMessage = millis();

            if (!gateOnline) {
                gateOnline = true;
                mqtt.publish(TOPIC_ONLINE, "online", true);
                Serial.println("Gate came online");
            }

            // Send ACK
            char ackBuf[16];
            formatAckMessage(ackBuf, seq);
            if (lora_idle) {
                lora_idle = false;
                Radio.Send((uint8_t *)ackBuf, strlen(ackBuf));
            }

            // Publish to MQTT
            publishStatus();
        }
    } else if (msgType == MSG_ACK) {
        // Command ACK received
        uint16_t ackSeq = 0;
        if (sscanf(rxpacket, "A|%hu", &ackSeq) == 1) {
            if (ackSeq == pendingCmdSeq) {
                Serial.println("Command ACK received");
                pendingCmdSeq = 0;
                cmdRetryCount = 0;
            }
        }
    }

    lora_idle = true;
}
