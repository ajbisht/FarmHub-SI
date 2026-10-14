# FarmHub AI – POC Architecture Review

**Reviewed document:** FARMHUB_SOLUTION_ARCHITECTURE_AND_REVIEW.md
**Author:** Ajay Bisht
**Review scope:** Proof of Concept (POC) only, meaning one small plot or bed in the village. This is **not** a full-field rollout.
**Review date:** 14 Oct 2026

---

## 1. What the POC Needs to Prove

For a POC, the design only needs to show these five things work end to end:

| # | POC goal | Covered in design? |
|---|----------|--------------------|
| 1 | Sensors read soil moisture and tank level reliably | ✅ Yes |
| 2 | The edge device waters safely without the cloud | ✅ Yes (strong) |
| 3 | Telemetry reaches the cloud and shows on a dashboard | ✅ Yes |
| 4 | AI takes in sensors, weather and images to make a useful decision | ⚠️ Partly. The LLM only writes a short message |
| 5 | Camera captures crop images that are used in the decision | ⚠️ Capture yes. Use in the decision isn't defined |

**Verdict:** For a POC, the architecture is **well designed and well scoped**. The hardware, cost and safety approach are right for this stage. The main gap is the **"Agentic AI"** part, which is the core of what you're trying to prove.

---

## 2. Research Notes (Key Technical Facts Checked)

| Topic | Finding | Impact on POC |
|-------|---------|---------------|
| ESP32 ADC2 vs Wi-Fi | ADC2 can't be used while Wi-Fi is active. ADC1 (GPIO 32–39) is safe | ✅ Design correctly uses GPIO34 (ADC1) |
| ESP32 ADC accuracy | The ADC is non-linear and noisy, especially near 0V and 3.3V | ⚠️ Average several samples (e.g., 10–20) and calibrate |
| Capacitive soil sensor v1.2 | Doesn't corrode like resistive sensors, but readings depend on soil type. Some cheap boards have a faulty voltage regulator or timer chip | ⚠️ Calibrate dry vs wet in your actual soil; buy 2 spares |
| 5V relay module on 3.3V GPIO | Many active-LOW 5V modules don't switch off fully at 3.3V logic and may click on during boot | ⚠️ Test early, or use a 3.3V-compatible relay or MOSFET module |
| ESP32 boot-time pin behaviour | Some GPIOs toggle during boot. GPIO18 is generally safe, but the relay may glitch before the firmware sets the pin | ⚠️ Set the pin HIGH as the very first line in `setup()` |
| ESP32-CAM power | Needs a stable 5V supply that can handle current spikes. A weak supply causes brownout resets | ⚠️ Give the camera node its own USB supply |
| Flyback diode | Protects against voltage spikes, but doesn't prevent relay contacts welding shut | ℹ️ For a POC, a fuse plus a 30s watchdog is acceptable |
| Cloud Run scale-to-zero | Cold starts take a few seconds. Fine for telemetry every 1–5 minutes | ✅ Acceptable for a POC |
| HTTP vs MQTT | HTTP is simpler and works well with Cloud Run. MQTT needs a broker that is always running | ✅ Keep HTTP for the POC |
| Open-Meteo | Free, needs no API key, and gives hourly rain probability | ✅ Good choice |
| Gemini 2.5 Flash multimodal | Can analyse a JPEG for leaf yellowing or wilting at low cost | ✅ Use the cloud. Skip TinyML for the POC |

---

## 3. Positives ✅

### 3.1 Safety-first edge design (biggest strength)
- The float-switch dry-run lock, 30-second pump limit, 2-hour cooldown and sensor-fault detection all run **locally on the ESP32**.
- If the internet or cloud goes down, the pump can't flood the plants or run dry.
- This is the correct pattern for any AI + IoT actuation system.

### 3.2 AI advises, but rules decide
- Fixed Python rules (crop profile, cooldown, rain forecast) run **before** the LLM.
- The LLM can't directly switch the pump. This avoids AI mistakes causing physical damage.

### 3.3 Split-node hardware choice
- The irrigation node (ESP32) and the camera node (ESP32-CAM) are separate.
- This avoids running out of pins, the ADC2/Wi-Fi conflict and camera-related brownouts.
- If the camera crashes, irrigation keeps working.

### 3.4 Right-sized hardware for a POC
- The total cost is about **₹1,527**, which is very affordable for a test.
- It uses a capacitive soil sensor (not the corroding resistive type), an optocoupler relay and a flyback diode.
- A breadboard is fine at POC stage.

### 3.5 Weather-aware decisions
- Using the rain forecast to skip watering shows real value early in the POC.

### 3.6 Good telemetry and observability
- The payload includes RSSI, free memory, uptime, Wi-Fi reconnect count and pump-cycle stats.
- This makes debugging the POC much easier.

### 3.7 Config-driven crops
- `crops_config.json` lets you change crop thresholds without changing code.

### 3.8 Lightweight, low-cost stack
- Vanilla HTML/JS dashboard, Cloud Run scaling to zero, and a free weather API.
- This fits the goal of keeping cloud cost low.

### 3.9 Good documentation
- The failure-mode table (FMEA), state machine diagram, pinout and JSON schemas are clear.
- The document is ready for review.

---

## 4. Negatives / Gaps ❌

> Field-scale concerns (LoRa, large pumps, multiple zones, IP65 enclosures) are **intentionally excluded** because this is a POC.

### 4.1 The "Agentic AI" part is thin (main gap) 🔴
- Right now the LLM only writes a **status sentence under 12 words**. A simple template could do the same job.
- There is no tool use, planning, memory or multi-step reasoning, so the POC won't **prove** Agentic AI yet.
- **Fix:** Give the agent tools:
  - `get_sensor_readings()`
  - `get_weather_forecast()`
  - `analyze_crop_image()`
  - `get_watering_history()`
  - `propose_irrigation(duration)` → checked by the safety rules
  - `send_alert(message)`
- Let it reason through a loop like: *"Soil is dry → check rain → check leaf image → check last 24h history → propose 20s watering → explain why."*

### 4.2 Camera images aren't part of the decision 🔴
- The camera captures images, but the design doesn't say how the image result changes any decision.
- **Fix:** Send the image to Gemini Vision, get a simple result such as `{health: ok | yellowing | wilting}`, and feed it into the agent's decision.

### 4.3 Cooldown is lost after a reboot 🟠
- The cooldown uses `millis()`, which resets on a power cut or reboot. After a power cut, the device may water again straight away.
- Village power cuts make this likely to happen even during the POC.
- **Fix:** Save the last watering time to the ESP32's flash memory (NVS / `Preferences`), or sync time using NTP.

### 4.4 Relay compatibility risk 🟠
- A 5V active-LOW relay driven from a 3.3V ESP32 pin may not switch reliably, and it may trigger briefly during boot.
- **Fix:** Test it on day one. Set GPIO18 HIGH at the very start of `setup()`. If it's still unreliable, use a 3.3V relay or a logic-level MOSFET module.

### 4.5 A stuck relay has no hardware backstop 🟡
- If the relay contacts weld shut, the software watchdog can't stop the pump.
- **For the POC:** Add an inline fuse and keep someone watching during testing. This is acceptable for now.

### 4.6 Shared power supply 🟡
- Both ESPs, the relay and the pump share one 5V 2.5A adapter.
- **Fix:** Power the ESP32-CAM from a separate USB charger.

### 4.7 BOM inconsistencies 🟡
| Mentioned in design | Missing from BOM |
|---|---|
| `temperature_c`, `humidity_pct` in telemetry | No DHT22 or SHT31 sensor (₹150–250) |
| 1000µF capacitor in the FMEA | Not listed |
| 12V pump option | No 12V supply |
| Pump fuse in the FMEA | Not listed |

### 4.8 Soil calibration not defined 🟡
- "VWC %" isn't meaningful without calibrating the sensor in your actual soil.
- **Fix:** Record the dry-soil and saturated-soil ADC values, then map between them. Average 10–20 samples per reading.

### 4.9 Cloud can override safety limits 🟡
- The actuation payload includes a `bypass_cooldown` field. The edge device should **never** accept any cloud command that relaxes its safety limits.
- The auth token sits inside the JSON body instead of an HTTP header. That's fine for a POC, but note it for later.

### 4.10 Minor unclear areas 🟢
- The "pre-calculated policy cache" isn't defined.
- It's not decided whether data goes to Firestore or Cloud Storage. **Pick Firestore** for the POC.
- There's no alert when a node goes offline. Add a simple "no data for 15 minutes" alert on Telegram.
- The <300 ms LLM latency target is unrealistic. **Plan for 1–3 seconds**, which is fine because it runs asynchronously.

---

## 5. Answers to the Five Review Questions (POC Context)

| # | Question | Recommendation for POC |
|---|----------|------------------------|
| 1 | Split-node vs single ESP32-S3? | **Keep the split-node design.** It's simpler to debug and the physical placement makes sense. Consider an ESP32-S3 only for a later production version |
| 2 | Are the safety guardrails enough? | **Yes for the POC**, with three additions: save the cooldown to flash, add an inline fuse, and ignore `bypass_cooldown` |
| 3 | HTTP vs MQTT? | **Stay on HTTP** to Cloud Run. Telemetry every 1–5 minutes, sent without waiting for a reply. MQTT isn't needed yet |
| 4 | Edge TinyML vs cloud vision? | **Use cloud vision (Gemini Flash).** Capture 2–4 images a day in daylight. TinyML is too much effort for a POC |
| 5 | OTA updates? | **Not needed for the POC.** Flash over USB. Later, have the device pull firmware updates over HTTPS from Cloud Storage, which needs no open ports |

---

## 6. Recommended POC Changes (Priority Order)

| Priority | Change | Effort | Cost |
|---|---|---|---|
| 1 | Turn the LLM into a tool-calling agent (Section 4.1) | Medium | Low (Gemini Flash) |
| 2 | Feed the camera result into the agent's decision | Medium | Low |
| 3 | Save the cooldown and last watering time in NVS | Low | ₹0 |
| 4 | Test the relay at 3.3V and set the pin safe at boot | Low | ₹0–100 |
| 5 | Separate USB power for the ESP32-CAM | Low | ₹150 |
| 6 | Add a DHT22, a 1000µF capacitor and an inline fuse | Low | ~₹250 |
| 7 | Calibrate the soil sensor and average readings | Low | ₹0 |
| 8 | Block `bypass_cooldown` at the edge | Low | ₹0 |
| 9 | Telegram alert when a node goes offline | Low | ₹0 |

---

## 7. Suggested POC Success Criteria

- [ ] The pump never runs when the tank is empty (tested 5 times)
- [ ] The pump stops within 30s even if the Wi-Fi is disconnected mid-cycle
- [ ] There's no double watering after a forced power cut
- [ ] Moisture readings stay within ±5% between repeated readings
- [ ] Watering is skipped when the rain probability is above 70%
- [ ] The agent's decision mentions sensor, weather **and** image inputs
- [ ] The dashboard shows live data, and a Telegram alert arrives for a low tank or an offline node
- [ ] The system runs for 7 days without manual reset

---

## 8. Final Verdict

| Area | Rating |
|---|---|
| Edge safety design | ⭐⭐⭐⭐⭐ |
| Hardware choice for a POC | ⭐⭐⭐⭐ |
| Cloud and dashboard | ⭐⭐⭐⭐ |
| Documentation | ⭐⭐⭐⭐⭐ |
| Agentic AI depth | ⭐⭐ |
| Use of camera images | ⭐⭐ |

**Overall:** It's a strong POC foundation. Make the AI layer genuinely agentic (tools, reasoning, and using the camera images) and fix the few small edge issues. After that, the POC will clearly prove the **IoT + Agentic AI** idea.
