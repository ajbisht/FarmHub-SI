#ifndef FARMHUB_CONFIG_H
#define FARMHUB_CONFIG_H

// ==============================================================================
// ESP32 GPIO PIN ASSIGNMENTS
// ==============================================================================
// Capacitive Soil Moisture Sensor (Analog Input)
#define PIN_SOIL_ADC       34

// Vertical Float Switch Sensor (Digital Input with external 10k pull-up to 3.3V)
#define PIN_FLOAT_SWITCH   35

// 5V Single-Channel Relay Module (Signal Input - controls 12V pump power)
#define PIN_RELAY_PUMP     25

// ==============================================================================
// SENSOR CALIBRATION VALUES
// (Tune these during Stage C1 calibration procedure)
// ==============================================================================
// Raw ADC reading in dry air (0% moisture)
#define CAL_DRY_AIR        2800

// Raw ADC reading submerged in a glass of water up to line (100% moisture)
#define CAL_IN_WATER       1100

// ==============================================================================
// TIMING & POWER SAVING (DEEP SLEEP)
// ==============================================================================
// Sleep duration between sensor readings (in seconds): 600s = 10 minutes
#define SLEEP_DURATION_SEC 600

// Stay awake window after publishing to listen for incoming pump commands (seconds)
#define AWAKE_WINDOW_SEC   20

// Max safe pump runtime hardcoded in firmware (safety cut-off: 45 seconds)
#define FIRMWARE_MAX_PUMP_SEC 45

// ==============================================================================
// NETWORK & MQTT CONFIGURATION
// (Enter your mobile phone hotspot credentials here)
// ==============================================================================
#define WIFI_SSID          "Your_Hotspot_Name"
#define WIFI_PASSWORD      "Your_Hotspot_Password"

// MQTT Broker IP or Hostname (Use the Pi's hotspot IP, e.g., "192.168.43.50", or test broker)
#define MQTT_BROKER_HOST   "broker.hivemq.com"
#define MQTT_BROKER_PORT   1883

// MQTT Topics
#define TOPIC_SOIL_MOISTURE     "farm/soil/moisture"
#define TOPIC_DRUM_LEVEL        "farm/drum/level"
#define TOPIC_PUMP_COMMAND      "farm/pump/command"
#define TOPIC_PUMP_ACK          "farm/pump/ack"
#define TOPIC_STATUS_HEARTBEAT  "farm/status/heartbeat"

#endif // FARMHUB_CONFIG_H
