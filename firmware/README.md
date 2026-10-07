# ESP32 Field Node Firmware — PlatformIO Guide

This folder contains the complete, production-ready C++ firmware for the **ESP32 DevKit V1 (30-pin)** controlling the sensors and 12V pump relay.

---

## 1. Prerequisites (Tools Needed on PC)

1. **VS Code** (which you already use).
2. Install the **PlatformIO IDE** extension in VS Code:
   * Open the Extensions tab in VS Code (`Ctrl + Shift + X`).
   * Search for `PlatformIO IDE` and click **Install**.
   * Restart VS Code when prompted.

---

## 2. Setting Up Your WiFi Hotspot Credentials

Before flashing, open [`firmware/src/config.h`](file:///c:/Users/ajay_bisht/RasberryPI/firmware/src/config.h) and set your 2.4 GHz hotspot details:

```cpp
#define WIFI_SSID          "Your_Phone_Hotspot_Name"
#define WIFI_PASSWORD      "Your_Hotspot_Password"

// When bench-testing before the Pi arrives, use the test broker:
#define MQTT_BROKER_HOST   "broker.hivemq.com"

// When running with the Raspberry Pi, use the Pi's hotspot IP:
// #define MQTT_BROKER_HOST   "192.168.43.50"
```

---

## 3. Flashing the ESP32 (One-Click)

1. Connect the ESP32 to your PC using a standard **Micro-USB data cable**.
2. Open the project in VS Code. PlatformIO will automatically detect the board from [`platformio.ini`](file:///c:/Users/ajay_bisht/RasberryPI/firmware/platformio.ini).
3. At the bottom toolbar of VS Code (PlatformIO blue status bar):
   * Click **✓ (PlatformIO: Build)** to compile the code.
   * Click **➔ (PlatformIO: Upload)** to flash it to your ESP32.
   * Click **🔌 (PlatformIO: Serial Monitor)** to view live debug logs at `115200` baud.

---

## 4. What the Firmware Does Automatically:

1. **Wakes Up:** Boots every 10 minutes from Deep Sleep.
2. **Fail-Safe:** Immediately ensures the Relay is `LOW` (pump powered off).
3. **Reads Sensors:**
   * Reads capacitive moisture sensor (takes 16 ADC samples on GPIO34 and averages them).
   * Reads float switch on GPIO35 (`OK` vs `LOW`).
4. **Connects to WiFi & MQTT:** Publishes the readings to `farm/soil/moisture`, `farm/drum/level`, and `farm/status/heartbeat`.
5. **20-Second Command Window:** Stays awake for 20 seconds listening for pump commands:
   * If a `RUN` command arrives and the drum is `OK`: turns on the relay for the requested duration, then turns it off and publishes `farm/pump/ack`.
   * If drum is `LOW`: vetoes the command to protect the pump.
6. **Sleeps:** Enters ultra-low-power **Deep Sleep** for 10 minutes to conserve the 12V battery.
