/*
 * Gate Protocol - Shared LoRa Message Protocol
 *
 * Common definitions for gate node and house gateway communication.
 * Copy this file to both Arduino sketch folders or use as a library.
 */

#ifndef GATE_PROTOCOL_H
#define GATE_PROTOCOL_H

#include <Arduino.h>

// LoRa Configuration (915MHz US ISM band)
#define RF_FREQUENCY        915000000
#define TX_OUTPUT_POWER     14          // dBm (max 20)
#define LORA_BANDWIDTH      0           // 125 kHz
#define LORA_SPREADING_FACTOR 9         // SF9 for better range
#define LORA_CODINGRATE     1           // 4/5
#define LORA_PREAMBLE_LENGTH 8
#define LORA_SYMBOL_TIMEOUT 0
#define LORA_FIX_LENGTH_PAYLOAD_ON false
#define LORA_IQ_INVERSION_ON false
#define BUFFER_SIZE         64

// Message Types
#define MSG_STATUS      'S'     // Gate status update
#define MSG_HEARTBEAT   'H'     // Periodic keepalive
#define MSG_COMMAND     'C'     // Control command
#define MSG_ACK         'A'     // Acknowledgment
#define MSG_ERROR       'E'     // Error report

// Gate States
#define STATE_UNKNOWN   0
#define STATE_CLOSED    1
#define STATE_OPEN      2
#define STATE_MOVING    3
#define STATE_ERROR     4

// Commands
#define CMD_OPEN        1
#define CMD_CLOSE       2
#define CMD_STOP        3
#define CMD_STATUS      4       // Request status

// Timing (milliseconds)
#define HEARTBEAT_INTERVAL  30000   // 30 seconds
#define ACK_TIMEOUT         5000    // 5 seconds
#define RETRY_COUNT         3
#define DEBOUNCE_TIME       50      // 50ms for limit switches

// Battery thresholds (millivolts)
#define BATTERY_FULL        13800   // 13.8V fully charged
#define BATTERY_NOMINAL     12600   // 12.6V nominal
#define BATTERY_LOW         11500   // 11.5V low warning
#define BATTERY_CRITICAL    11000   // 11.0V critical

// Node identifiers
#define NODE_GATE       0x01
#define NODE_GATEWAY    0x02

// Message structure
typedef struct {
    uint8_t type;           // Message type (S, H, C, A, E)
    uint8_t node_id;        // Source node
    uint16_t sequence;      // Sequence number for ACK matching
    uint8_t state;          // Gate state
    uint16_t battery_mv;    // Battery voltage in millivolts
    uint8_t command;        // Command (for CMD messages)
    int16_t rssi;           // RSSI of last received message
    int8_t snr;             // SNR of last received message
} GateMessage;

// Helper functions
inline const char* stateToString(uint8_t state) {
    switch (state) {
        case STATE_CLOSED:  return "CLOSED";
        case STATE_OPEN:    return "OPEN";
        case STATE_MOVING:  return "MOVING";
        case STATE_ERROR:   return "ERROR";
        default:            return "UNKNOWN";
    }
}

inline const char* commandToString(uint8_t cmd) {
    switch (cmd) {
        case CMD_OPEN:   return "OPEN";
        case CMD_CLOSE:  return "CLOSE";
        case CMD_STOP:   return "STOP";
        case CMD_STATUS: return "STATUS";
        default:         return "UNKNOWN";
    }
}

// Simple message formatting (pipe-delimited for easy parsing)
// STATUS:    S|<state>|<battery_mv>|<seq>
// HEARTBEAT: H|<state>|<battery_mv>|<seq>
// COMMAND:   C|<cmd>|<seq>
// ACK:       A|<seq>

inline int formatStatusMessage(char* buf, uint8_t state, uint16_t battery_mv, uint16_t seq) {
    return sprintf(buf, "S|%d|%u|%u", state, battery_mv, seq);
}

inline int formatHeartbeatMessage(char* buf, uint8_t state, uint16_t battery_mv, uint16_t seq) {
    return sprintf(buf, "H|%d|%u|%u", state, battery_mv, seq);
}

inline int formatCommandMessage(char* buf, uint8_t cmd, uint16_t seq) {
    return sprintf(buf, "C|%d|%u", cmd, seq);
}

inline int formatAckMessage(char* buf, uint16_t seq) {
    return sprintf(buf, "A|%u", seq);
}

#endif // GATE_PROTOCOL_H
