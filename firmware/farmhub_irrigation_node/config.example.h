#pragma once


// ============================================================================
// FarmHub AI — Node 1 (Irrigation & Telemetry) Configuration Template
// Copy this file to "config.h" and insert your local Wi-Fi and Cloud Run details.
// ============================================================================

// 1. Wi-Fi Credentials
#define WIFI_SSID           "YOUR_WIFI_SSID"
#define WIFI_PASSWORD       "YOUR_WIFI_PASSWORD"

// 2. Cloud Run API Endpoint (Backend URL)
#define FARHUB_API_URL      "https://farmhub-agent-xxx-asia-south1.a.run.app/api/telemetry"
#define DEVICE_AUTH_TOKEN   "farmhub-edge-node-01-token"

// 3. Hardware Pin Mapping (ESP32 30-Pin CP2102)
#define PIN_SOIL_ADC        34    // ADC1_CH6 (Safe with Wi-Fi active)
#define PIN_FLOAT_SWITCH    19    // Internal Pull-Up, connects to GND when water normal
#define PIN_RELAY           18    // Active-LOW trigger for 5V Relay module
#define PIN_STATUS_LED       2    // Onboard blue LED for status indication

// 4. Capacitive Soil Moisture Calibration (12-bit ADC: 0 - 4095)
// Record these values by testing the sensor in dry air vs. cup of wet soil
#define ADC_RAW_DRY_AIR     3200  // ADC reading in completely dry air (0% VWC)
#define ADC_RAW_SATURATED   1450  // ADC reading submerged in saturated wet soil (100% VWC)

// 5. Hardware Safety Limits (Enforced locally on bare silicon)
#define MAX_PUMP_RUN_SEC      30  // Hard watchdog cutoff (never pump longer than 30s)
#define COOLDOWN_MINUTES     120  // 2-hour mandatory hydraulic cooldown between cycles
#define TELEMETRY_INTERVAL_MS 60000 // Report telemetry every 60 seconds
#define SAMPLE_COUNT          16  // Number of ADC readings averaged per sample
