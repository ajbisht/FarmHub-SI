#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "config.h"

// Hardware clients
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// Global State
float currentMoisturePct = 0.0;
int currentRawADC = 0;
bool isDrumOk = true;
bool pumpCommandExecuted = false;

// Function Declarations
void connectWiFi();
void connectMQTT();
void readSensors();
void publishTelemetry();
void mqttCallback(char* topic, byte* payload, unsigned int length);
void enterDeepSleep();

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n==================================================");
    Serial.println(" FarmHub ESP32 Field Node — Waking Up...");
    Serial.println("==================================================");

    // 1. Configure Hardware Pins (Fail-Safe: Pump Relay stays OFF!)
    pinMode(PIN_RELAY_PUMP, OUTPUT);
    digitalWrite(PIN_RELAY_PUMP, LOW); // Relay OFF

    pinMode(PIN_FLOAT_SWITCH, INPUT);  // Float switch input
    pinMode(PIN_SOIL_ADC, INPUT);       // Capacitive soil sensor analog input

    // 2. Read physical sensors immediately
    readSensors();

    // 3. Connect to 2.4 GHz WiFi Hotspot
    connectWiFi();

    // 4. Configure MQTT
    mqttClient.setServer(MQTT_BROKER_HOST, MQTT_BROKER_PORT);
    mqttClient.setCallback(mqttCallback);
    connectMQTT();

    // 5. Broadcast Telemetry Packet to Agent & Dashboard
    publishTelemetry();

    // 6. Active Listening Window (Stay awake 20 seconds for pump commands)
    Serial.printf("[FIRMWARE] Staying awake for %d seconds to listen for commands...\n", AWAKE_WINDOW_SEC);
    unsigned long startAwakeTime = millis();
    while (millis() - startAwakeTime < (AWAKE_WINDOW_SEC * 1000UL)) {
        if (!mqttClient.connected()) {
            connectMQTT();
        }
        mqttClient.loop();
        delay(50);
    }

    // 7. Power-Saving: Enter Deep Sleep for 10 minutes
    enterDeepSleep();
}

void loop() {
    // Empty: ESP32 sleeps at the end of setup()
}

// ==============================================================================
// SENSOR READING & ADC AVERAGING
// ==============================================================================
void readSensors() {
    // Sample soil ADC 16 times with small delay to smooth out voltage ripple
    long adcSum = 0;
    for (int i = 0; i < 16; i++) {
        adcSum += analogRead(PIN_SOIL_ADC);
        delay(10);
    }
    currentRawADC = adcSum / 16;

    // Invert ADC reading: lower ADC = higher moisture
    // CAL_DRY_AIR (~2800) = 0%, CAL_IN_WATER (~1100) = 100%
    float pct = (float)(CAL_DRY_AIR - currentRawADC) / (float)(CAL_DRY_AIR - CAL_IN_WATER) * 100.0f;
    currentMoisturePct = constrain(pct, 0.0f, 100.0f);

    // Read Float Switch (pulled up to 3.3V)
    // HIGH with pull-up = Switch open (water level dropped LOW)
    // LOW = Switch closed to GND (water level is OK)
    int floatState = digitalRead(PIN_FLOAT_SWITCH);
    isDrumOk = (floatState == LOW);

    Serial.printf("[SENSORS] Soil ADC: %d -> Moisture: %.1f%%\n", currentRawADC, currentMoisturePct);
    Serial.printf("[SENSORS] Drum Float Switch: %s\n", isDrumOk ? "OK" : "LOW");
}

// ==============================================================================
// NETWORK & MQTT ROUTINES
// ==============================================================================
void connectWiFi() {
    Serial.printf("[WIFI] Connecting to SSID: %s ", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 25) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WIFI] Connected! IP: %s (RSSI: %d dBm)\n",
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.println("\n[WIFI] Connection timed out! Continuing to fail-safe sleep.");
        enterDeepSleep();
    }
}

void connectMQTT() {
    int retries = 0;
    while (!mqttClient.connected() && retries < 3) {
        String clientId = "esp32_field_node_" + String(random(1000, 9999));
        Serial.printf("[MQTT] Connecting to %s:%d... ", MQTT_BROKER_HOST, MQTT_BROKER_PORT);

        if (mqttClient.connect(clientId.c_str())) {
            Serial.println("Connected!");
            mqttClient.subscribe(TOPIC_PUMP_COMMAND, 1);
        } else {
            Serial.printf("Failed, rc=%d. Retrying in 2s...\n", mqttClient.state());
            delay(2000);
            retries++;
        }
    }
}

void publishTelemetry() {
    if (!mqttClient.connected()) return;

    // 1. Soil Moisture Payload
    JsonDocument soilDoc;
    soilDoc["moisture_pct"] = round(currentMoisturePct * 10.0) / 10.0;
    soilDoc["raw"] = currentRawADC;
    soilDoc["simulated"] = false;
    soilDoc["ts"] = millis();
    char soilBuf[128];
    serializeJson(soilDoc, soilBuf);
    mqttClient.publish(TOPIC_SOIL_MOISTURE, soilBuf, true);
    Serial.printf("[MQTT] Published %s -> %s\n", TOPIC_SOIL_MOISTURE, soilBuf);

    // 2. Drum Level Payload
    JsonDocument drumDoc;
    drumDoc["level"] = isDrumOk ? "OK" : "LOW";
    drumDoc["simulated"] = false;
    drumDoc["ts"] = millis();
    char drumBuf[128];
    serializeJson(drumDoc, drumBuf);
    mqttClient.publish(TOPIC_DRUM_LEVEL, drumBuf, true);
    Serial.printf("[MQTT] Published %s -> %s\n", TOPIC_DRUM_LEVEL, drumBuf);

    // 3. Status Heartbeat Payload
    JsonDocument statusDoc;
    statusDoc["battery_v"] = 12.2; // Can read via voltage divider on future revision
    statusDoc["rssi"] = WiFi.RSSI();
    statusDoc["simulated"] = false;
    statusDoc["ts"] = millis();
    char statusBuf[128];
    serializeJson(statusDoc, statusBuf);
    mqttClient.publish(TOPIC_STATUS_HEARTBEAT, statusBuf, false);
}

// ==============================================================================
// INCOMING COMMAND CALLBACK & RELAY ACTUATION
// ==============================================================================
void mqttCallback(char* topic, byte* payload, unsigned int length) {
    if (strcmp(topic, TOPIC_PUMP_COMMAND) != 0) return;

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, payload, length);
    if (error) {
        Serial.printf("[MQTT] JSON parse error: %s\n", error.c_str());
        return;
    }

    const char* action = doc["action"];
    int durationSec = doc["duration_sec"] | 30;

    Serial.printf("[ACTUATION] Command received: action=%s, duration=%ds\n", action, durationSec);

    if (strcmp(action, "RUN") == 0) {
        // Hardware Safety Guard: Never run pump if drum is LOW!
        if (!isDrumOk) {
            Serial.println("[SAFETY VETO] Command BLOCKED: Drum water level is LOW!");
            return;
        }

        // Clamp duration to firmware safe limit
        if (durationSec > FIRMWARE_MAX_PUMP_SEC) {
            durationSec = FIRMWARE_MAX_PUMP_SEC;
            Serial.printf("[SAFETY CLAMP] Duration clamped to %ds.\n", FIRMWARE_MAX_PUMP_SEC);
        }

        Serial.printf("[PUMP] Activating relay (GPIO%d HIGH) for %d seconds...\n", PIN_RELAY_PUMP, durationSec);
        digitalWrite(PIN_RELAY_PUMP, HIGH); // Pump ON

        // Maintain MQTT keepalives while pumping
        unsigned long pumpStart = millis();
        while (millis() - pumpStart < (durationSec * 1000UL)) {
            mqttClient.loop();
            delay(100);
        }

        digitalWrite(PIN_RELAY_PUMP, LOW);  // Pump OFF
        Serial.println("[PUMP] Pump deactivated (GPIO LOW).");

        // Publish Ack
        JsonDocument ackDoc;
        ackDoc["action"] = "COMPLETED";
        ackDoc["duration_sec"] = durationSec;
        ackDoc["simulated"] = false;
        ackDoc["ts"] = millis();
        char ackBuf[128];
        serializeJson(ackDoc, ackBuf);
        mqttClient.publish(TOPIC_PUMP_ACK, ackBuf, false);
        Serial.printf("[MQTT] Published ACK -> %s\n", ackBuf);

        pumpCommandExecuted = true;
    }
    else if (strcmp(action, "STOP") == 0) {
        digitalWrite(PIN_RELAY_PUMP, LOW);
        Serial.println("[PUMP] Immediate emergency STOP executed.");
    }
}

// ==============================================================================
// DEEP SLEEP ROUTINE
// ==============================================================================
void enterDeepSleep() {
    Serial.println("[POWER] Ensuring relay is OFF before sleep (Fail-Safe)...");
    digitalWrite(PIN_RELAY_PUMP, LOW);

    mqttClient.disconnect();
    WiFi.disconnect(true);

    Serial.printf("[POWER] Entering ESP32 Deep Sleep for %d seconds (%d minutes)...\n",
                  SLEEP_DURATION_SEC, SLEEP_DURATION_SEC / 60);
    Serial.flush();

    // Enable timer wakeup (microsecond precision)
    esp_sleep_enable_timer_wakeup(SLEEP_DURATION_SEC * 1000000ULL);
    esp_deep_sleep_start();
}
