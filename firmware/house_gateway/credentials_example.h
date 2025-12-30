/*
 * WiFi and MQTT Credentials - EXAMPLE FILE
 *
 * Copy this file to 'credentials.h' and fill in your actual values.
 * The credentials.h file is gitignored and will not be committed.
 *
 *   cp credentials_example.h credentials.h
 *   # Then edit credentials.h with your actual values
 */

#ifndef CREDENTIALS_H
#define CREDENTIALS_H

// WiFi Configuration
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"

// MQTT Configuration
#define MQTT_SERVER     "192.168.1.100"  // Raspberry Pi IP address
#define MQTT_PORT       1883
#define MQTT_USER       ""               // Leave empty if no auth
#define MQTT_PASSWORD   ""               // Leave empty if no auth
#define MQTT_CLIENT_ID  "gate_gateway"

#endif // CREDENTIALS_H
