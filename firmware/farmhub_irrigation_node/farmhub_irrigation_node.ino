// ============================================================================
// FarmHub AI — Node 1: Precision Irrigation & Telemetry Firmware (MVP)
// Hardware: ESP32-WROOM-32D (30-Pin CP2102)
// Features: NVS Cooldown Persistence, Multi-Sample ADC1, Active-LOW Safe Boot,
//           Float-Switch Cutoff, 30s Watchdog, Closed-Loop Soil Delta Tracker
// ============================================================================

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <time.h>
#include "config.h"

// --- Global State & Hardware Handles ---
Preferences prefs;
HTTPClient http;

enum PumpState {
    PUMP_IDLE,
    PUMP_WATERING,
    PUMP_COOLDOWN,
    PUMP_EMERGENCY_STOP
};

PumpState current_pump_state = PUMP_IDLE;
unsigned long pump_start_millis = 0;
unsigned long active_run_target_sec = 0;
unsigned long last_telemetry_millis = 0;

// Persistent state loaded from NVS
unsigned long last_watered_epoch = 0;
uint16_t total_cycles_today = 0;

// Closed-loop verification state
float pre_irrigation_moisture = 0.0;
unsigned long post_check_scheduled_epoch = 0;
bool delivery_verified = true;
bool delivery_fault = false;

// ============================================================================
// 1. SETUP: SAFE BOOT & PERIPHERAL INITIALIZATION
// ============================================================================
void setup() {
    // CRITICAL SAFETY RULE 1: Initialize Relay Pin HIGH (OFF) on LINE 1
    // Active-LOW relays will click ON during boot if GPIO is left floating.
    pinMode(PIN_RELAY, OUTPUT);
    digitalWrite(PIN_RELAY, HIGH); // HIGH = Relay De-energized (Pump OFF)

    pinMode(PIN_STATUS_LED, OUTPUT);
    digitalWrite(PIN_STATUS_LED, LOW);

    // Float switch uses internal pull-up. 
    // Closed to GND = Tank Normal. Open = Tank Empty.
    pinMode(PIN_FLOAT_SWITCH, INPUT_PULLUP);

    Serial.begin(115200);
    delay(200);
    Serial.println("\n[FarmHub] Booting Node 1 Irrigation Controller...");

    // Configure 12-bit ADC on ADC1 (GPIO 34)
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db); // Full 0 - 3.3V range

    // 2. Initialize Non-Volatile Storage (NVS)
    prefs.begin("farmhub_node", false);
    last_watered_epoch = prefs.getULong("last_water", 0);
    total_cycles_today = prefs.getUShort("cycles_today", 0);
    Serial.printf("[NVS] Loaded: Last Watered Epoch=%lu, Cycles Today=%u\n", 
                  last_watered_epoch, total_cycles_today);

    // 3. Connect to Local 2.4 GHz Wi-Fi
    connectWiFi();

    // 4. Synchronize NTP Time (IST = UTC+5:30 -> 19800s offset)
    configTime(19800, 0, "pool.ntp.org", "time.google.com");
    Serial.println("[NTP] Syncing network time...");
}

// ============================================================================
// 2. MAIN LOOP: CONTINUOUS SAFETY FSM & SENSOR MONITORING
// ============================================================================
void loop() {
    unsigned long now_millis = millis();
    time_t now_epoch = time(nullptr);

    // A. ALWAYS CHECK HARDWARE SAFETY FIRST
    bool reservoir_ok = isReservoirOk();
    if (!reservoir_ok && current_pump_state == PUMP_WATERING) {
        emergencyStop("Water reservoir empty during active pump cycle!");
    }

    // B. WATCHDOG TIMER FOR RUNNING PUMP
    if (current_pump_state == PUMP_WATERING) {
        unsigned long elapsed_sec = (now_millis - pump_start_millis) / 1000;
        if (elapsed_sec >= active_run_target_sec || elapsed_sec >= MAX_PUMP_RUN_SEC) {
            stopWateringCycle("Watchdog completed commanded watering cycle");
        }
    }

    // C. COOLDOWN STATE MONITORING
    unsigned long cooldown_seconds = COOLDOWN_MINUTES * 60UL;
    if (now_epoch > 100000 && last_watered_epoch > 0) {
        if ((now_epoch - last_watered_epoch) < cooldown_seconds) {
            current_pump_state = PUMP_COOLDOWN;
        } else if (current_pump_state == PUMP_COOLDOWN) {
            current_pump_state = PUMP_IDLE;
            Serial.println("[FSM] Cooldown period expired. Node ready for watering.");
        }
    }

    // D. CLOSED-LOOP WATER DELIVERY VERIFICATION
    if (post_check_scheduled_epoch > 0 && now_epoch >= post_check_scheduled_epoch) {
        verifySoilMoistureResponse();
    }

    // E. PERIODIC TELEMETRY DISPATCH (Default: every 60s)
    if (now_millis - last_telemetry_millis >= TELEMETRY_INTERVAL_MS) {
        last_telemetry_millis = now_millis;
        sendTelemetryPacket();
    }

    delay(20); // Yield to FreeRTOS background tasks
}

// ============================================================================
// 3. SENSOR READING & MULTI-SAMPLE ADC FILTERING
// ============================================================================
uint16_t readFilteredSoilADC() {
    uint32_t adc_sum = 0;
    for (int i = 0; i < SAMPLE_COUNT; i++) {
        adc_sum += analogRead(PIN_SOIL_ADC);
        delay(5);
    }
    return (uint16_t)(adc_sum / SAMPLE_COUNT);
}

float calculateSoilVWC(uint16_t raw_adc) {
    // Sanity check for disconnected probe
    if (raw_adc < 100 || raw_adc > 4050) {
        return -1.0; // SENSOR_FAULT indicator
    }

    // Capacitive sensor reads HIGHER voltage when dry, LOWER when wet
    if (raw_adc >= ADC_RAW_DRY_AIR) return 0.0;
    if (raw_adc <= ADC_RAW_SATURATED) return 100.0;

    float pct = (float)(ADC_RAW_DRY_AIR - raw_adc) / 
                (float)(ADC_RAW_DRY_AIR - ADC_RAW_SATURATED) * 100.0;
    return constrain(pct, 0.0, 100.0);
}

bool isReservoirOk() {
    // Float switch: Closed (LOW) when float is buoyant, Open (HIGH) when dry
    return (digitalRead(PIN_FLOAT_SWITCH) == LOW);
}

// ============================================================================
// 4. ACTUATION & HARDWARE INTERLOCK ENFORCEMENT
// ============================================================================
bool startWateringCycle(uint8_t duration_sec) {
    time_t now_epoch = time(nullptr);
    unsigned long cooldown_seconds = COOLDOWN_MINUTES * 60UL;

    // Hard Interlock 1: Dry Reservoir Check
    if (!isReservoirOk()) {
        Serial.println("[SAFETY] Blocked: Reservoir is empty.");
        return false;
    }

    // Hard Interlock 2: Cooldown Lockout Check (NVS-backed)
    if (now_epoch > 100000 && last_watered_epoch > 0) {
        if ((now_epoch - last_watered_epoch) < cooldown_seconds) {
            Serial.printf("[SAFETY] Blocked: In cooldown (%lu sec remaining).\n",
                          (unsigned long)(cooldown_seconds - (now_epoch - last_watered_epoch)));
            return false;
        }
    }

    // Hard Interlock 3: Clamp duration to hard maximum
    if (duration_sec > MAX_PUMP_RUN_SEC) {
        duration_sec = MAX_PUMP_RUN_SEC;
    }

    // Record pre-irrigation moisture for closed-loop verification
    uint16_t raw_adc = readFilteredSoilADC();
    pre_irrigation_moisture = calculateSoilVWC(raw_adc);

    // Energize Relay (Active-LOW: Pull LOW to turn ON)
    digitalWrite(PIN_RELAY, LOW);
    digitalWrite(PIN_STATUS_LED, HIGH);

    pump_start_millis = millis();
    active_run_target_sec = duration_sec;
    current_pump_state = PUMP_WATERING;

    Serial.printf("[ACTUATOR] Pump started for %u seconds.\n", duration_sec);
    return true;
}

void stopWateringCycle(const char* reason) {
    // De-energize Relay (Active-LOW: Pull HIGH to turn OFF)
    digitalWrite(PIN_RELAY, HIGH);
    digitalWrite(PIN_STATUS_LED, LOW);

    time_t now_epoch = time(nullptr);
    last_watered_epoch = now_epoch;
    total_cycles_today++;

    // Persist immediately to NVS Flash Memory (Immune to Power Cuts)
    prefs.putULong("last_water", last_watered_epoch);
    prefs.putUShort("cycles_today", total_cycles_today);

    current_pump_state = PUMP_COOLDOWN;
    Serial.printf("[ACTUATOR] Pump stopped: %s. State saved to NVS.\n", reason);

    // Schedule closed-loop soil moisture response verification in 20 minutes (1200s)
    post_check_scheduled_epoch = now_epoch + 1200;
}

void emergencyStop(const char* reason) {
    digitalWrite(PIN_RELAY, HIGH);
    digitalWrite(PIN_STATUS_LED, LOW);
    current_pump_state = PUMP_EMERGENCY_STOP;
    Serial.printf("[EMERGENCY STOP] %s\n", reason);
}

// ============================================================================
// 5. CLOSED-LOOP SOIL VERIFICATION
// ============================================================================
void verifySoilMoistureResponse() {
    uint16_t post_adc = readFilteredSoilADC();
    float post_moisture = calculateSoilVWC(post_adc);

    post_check_scheduled_epoch = 0; // Reset check schedule

    if (pre_irrigation_moisture < 0 || post_moisture < 0) {
        return; // Sensor fault, cannot evaluate
    }

    float delta = post_moisture - pre_irrigation_moisture;
    if (delta >= 2.5) {
        delivery_verified = true;
        delivery_fault = false;
        Serial.printf("[VERIFY] Delivery Confirmed: Moisture rose by +%.1f%%\n", delta);
    } else {
        delivery_verified = false;
        delivery_fault = true;
        Serial.printf("[VERIFY ALARM] Delivery Fault: Moisture delta only %.1f%% after watering!\n", delta);
    }
}

// ============================================================================
// 6. TELEMETRY & CLOUD COMMUNICATIONS
// ============================================================================
void connectWiFi() {
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 25) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected! IP: %s, RSSI: %d dBm\n", 
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
    } else {
        Serial.println("\n[WiFi] Connection timeout. Operating in autonomous offline mode.");
    }
}

void sendTelemetryPacket() {
    if (WiFi.status() != WL_CONNECTED) {
        connectWiFi();
        if (WiFi.status() != WL_CONNECTED) return;
    }

    uint16_t raw_adc = readFilteredSoilADC();
    float vwc = calculateSoilVWC(raw_adc);
    bool tank_ok = isReservoirOk();
    time_t now_epoch = time(nullptr);

    // Compute remaining cooldown seconds
    unsigned long cooldown_sec = COOLDOWN_MINUTES * 60UL;
    unsigned long cooldown_rem = 0;
    if (now_epoch > 100000 && last_watered_epoch > 0) {
        if ((now_epoch - last_watered_epoch) < cooldown_sec) {
            cooldown_rem = cooldown_sec - (now_epoch - last_watered_epoch);
        }
    }

    // Build JSON packet
    char payload[512];
    snprintf(payload, sizeof(payload),
        "{\"device_id\":\"farmhub-node-01\","
        "\"timestamp\":%lu,"
        "\"soil_moisture_vwc_pct\":%.1f,"
        "\"soil_raw_adc\":%u,"
        "\"reservoir_level_ok\":%s,"
        "\"pump_running\":%s,"
        "\"cooldown_remaining_sec\":%lu,"
        "\"total_cycles_today\":%u,"
        "\"delivery_verified\":%s,"
        "\"delivery_fault\":%s,"
        "\"rssi_dbm\":%d}",
        (unsigned long)now_epoch,
        vwc,
        raw_adc,
        tank_ok ? "true" : "false",
        (current_pump_state == PUMP_WATERING) ? "true" : "false",
        cooldown_rem,
        total_cycles_today,
        delivery_verified ? "true" : "false",
        delivery_fault ? "true" : "false",
        WiFi.RSSI()
    );

    Serial.printf("\n[Sensors] Soil Moisture: %.1f%% (Raw ADC: %u) | Drum Level: %s\n",
                  vwc, raw_adc, tank_ok ? "NORMAL (OK)" : "EMPTY (FAULT)");
    Serial.println("[Cloud] Dispatching telemetry to Cloud Run...");

    WiFiClientSecure secure_client;
    secure_client.setInsecure(); // Allow Cloud Run HTTPS without manual CA cert bundle

    HTTPClient http;
    http.begin(secure_client, FARHUB_API_URL);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", String("Bearer ") + DEVICE_AUTH_TOKEN);

    int httpCode = http.POST(payload);
    if (httpCode == HTTP_CODE_OK || httpCode == HTTP_CODE_CREATED) {
        String response = http.getString();
        Serial.printf("[Cloud] Telemetry POST 200 OK. Response: %s\n", response.c_str());

        // Check if response contains an authorized actuation command
        if (response.indexOf("IRRIGATE_CYCLE") >= 0) {
            // Parse duration (default 20s if not found)
            startWateringCycle(20);
        }
    } else {
        Serial.printf("[Cloud] Telemetry POST failed. Code: %d\n", httpCode);
    }
    http.end();
}
