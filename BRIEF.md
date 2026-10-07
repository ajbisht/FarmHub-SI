THE PROJECT IN ONE PARAGRAPH

A small, **self-funded POC** to prove an **Agentic AI loop with real sensors and no human in the loop** for watering **5 tomato plants**. A soil-moisture sensor and a drum water-level float feed an **ESP32 field node**. The ESP32 sends readings over **MQTT** to a **Raspberry Pi Zero 2 W**. A **Python agent** on the Pi adds history and weather, asks an **LLM (Groq, free tier)** whether to water, and sends a command back. The ESP32 opens a **12V solenoid valve** on a **gravity-fed 50 L drum** (7 ft above the plants). The agent then **verifies** that moisture actually rose. A **dashboard (PWA)** shows everything. This must use **real sensor data, not fake data** — a simulator is allowed only for early testing.

**Honest boundary (do not oversell):** watering is fully autonomous. Refilling the 50 L drum is NOT — the system only detects "drum low" and alerts me.

---

# 3. DECISIONS ALREADY MADE (treat as locked unless you find a real problem — then ask)

| Area | Decision |
|---|---|
| Crop / scale | 5 tomato plants, one small bed, **1 soil sensor** |
| Phase | **Phase 1 = irrigation loop + dashboard.** Camera / ripeness detection is **Phase 2 (out of scope now)** |
| Water source | Gravity-fed **50 L drum, ~7 ft (≈2.13 m, ≈0.21 bar)** above the valve |
| Field controller | **ESP32 DevKit V1 (30-pin)** |
| Sensors | **Capacitive soil moisture v2.0** (analog) + **float switch** in the drum (digital) |
| Actuator | **Standard 12V DC normally-closed solenoid valve (½")** switched by a **single 5V relay module** (we dropped the latching-valve / H-bridge idea) |
| Power (field) | 12V Li-ion pack (≈5200 mAh, with BMS) + LM2596 buck converter to 5V for the ESP32 |
| Home hub | **Raspberry Pi Zero 2 W**, Raspberry Pi OS Lite, hostname `farmhub.local`, SSH, **Mosquitto** broker |
| Messaging | **MQTT**, QoS 1. ESP32 never talks to the LLM or the internet APIs — **only the Agent does** |
| LLM | **Groq free tier** (open-weight model, e.g. gpt-oss-20b or qwen). Gemini Flash free tier as a fallback key. No paid API |
| Weather | OpenWeatherMap free tier |
| History | SQLite on the Pi |
| Dashboard | **PWA first** (works in the phone browser, no Android Studio). Native APK is a stretch goal |
| Network | My **phone hotspot** is the only network for the POC (I will stay near and trigger test situations myself) |
| Safety default | **No command from the agent = valve stays closed.** The ESP32 firmware must enforce this |
| Build style | **Two tracks in parallel:** Track A = hardware/firmware, Track B = software. They meet only at the MQTT contract (Section 5) |
| Deployment | Agent runs on the Pi as a **systemd service** (auto-start, auto-restart) |

**Environment constraints you must respect**
- ESP32 and Pi Zero 2 W are **2.4 GHz WiFi only** → my hotspot must be on the 2.4 GHz band.
- My office Ollama / local LLMs are **not** available. Cloud API only.
- Pi Zero 2 W has 512 MB RAM → keep the Pi software light.

---

# 4. OUT OF SCOPE (do not build, do not plan)

- Camera, fruit growth or ripeness detection (Phase 2)
- Robotic harvesting, or automatic drum refilling
- Multi-zone / multi-field scaling, LoRaWAN, solar charging
- Cloud hosting, user accounts, multi-user support
- Kubernetes, Docker orchestration, CI/CD pipelines
- Anything that needs a paid service

---

# 5. ARCHITECTURE & MQTT CONTRACT (baseline — challenge it in your questions if needed)

```
Soil sensor ─┐
Float switch ─┼─► ESP32 ──WiFi/MQTT──► Mosquitto (on Pi) ──► Python Agent (on Pi)
Valve+Relay ◄─┘                                               │  ├─ SQLite (history)
                                                              │  ├─ Weather API (HTTPS)
                                                              │  ├─ Groq LLM (HTTPS)
                                                              │  └─ Flask/FastAPI ─► PWA Dashboard
```

| Topic | Direction | Example payload |
|---|---|---|
| `farm/soil/moisture` | ESP32 → Agent | `{"moisture_pct":32,"raw":1450,"ts":"..."}` |
| `farm/drum/level` | ESP32 → Agent | `{"level":"OK"\|"LOW","ts":"..."}` |
| `farm/valve/command` | Agent → ESP32 | `{"action":"OPEN","duration_sec":45,"reason":"..."}` |
| `farm/valve/ack` | ESP32 → Agent | `{"action":"OPENED","duration_sec":45,"ts":"..."}` |
| `farm/verify/moisture` | ESP32 → Agent | `{"moisture_pct":51,"ts":"..."}` (~15 min after watering) |
| `farm/alert` | Agent → Dashboard | `{"type":"LOW_DRUM"\|"ANOMALY","message":"..."}` |
| `farm/status/heartbeat` | ESP32 → Agent | `{"battery_v":3.7,"ts":"..."}` |

**Pin map (single-relay version — supersedes my earlier 2-relay diagram):** soil AOUT→GPIO34, float→GPIO35 (needs 10 kΩ pull-up), relay IN→GPIO25, all grounds common.

**Agent cycle (every ~10 min):** sense → read history + weather → ask LLM → **validate the LLM answer in code** → command valve → wait ~15 min → verify moisture rose → log → push to dashboard. If drum is LOW → alert and do not water. If the LLM/network is unreachable → **do nothing, log, retry** (fail-safe).

---

# 6. PROPOSED STAGES (a starting point — you will confirm/modify these in your plan)

| Stage | Goal | Needs hardware? |
|---|---|---|
| **A1** | Project skeleton, config/.env, MQTT topic constants, **sensor simulator**, local Mosquitto test | No |
| **A2** | Agent core: MQTT subscriber, SQLite history, weather client, Groq client, **guardrail layer** (max duration, min gap between waterings, daily cap), fail-safe, verification scheduler, **dry-run mode** (commands logged, not executed) | No |
| **A3** | Dashboard backend + PWA: live moisture, drum status, last decisions with reasoning, history graph, manual override, alerts | No |
| **A4** | Pi deployment: systemd service, logs, restart behaviour, deploy steps | Pi only |
| **B1** | ESP32 firmware: read sensors, calibrate, MQTT publish/subscribe, relay control, fail-safe, power saving | ESP32 + sensors |
| **B2** | Bench test on desk: breadboard, no water, relay click test | Yes |
| **C1** | Integration: replace simulator with real ESP32, soil calibration (dry/wet) | Yes |
| **C2** | Field test with water and the demo scenarios below | Yes |

**POC demo scenarios (my definition of "done")**
1. Soil is dry → agent decides WATER → valve opens → moisture rises → logged as success.
2. Soil is wet / rain forecast → agent decides SKIP and explains why.
3. Drum float = LOW → alert on dashboard, no watering.
4. Valve fired but moisture did not rise → ANOMALY alert.
5. Internet/LLM unplugged → valve stays closed, system recovers by itself when back.
6. Pi reboot → agent service comes back on its own.

---

# 7. OPEN QUESTIONS — ASK ME THESE FIRST (with your recommended default for each)

**Batch 1 — Hardware behaviour**
1. **ESP32 sleep vs. receiving commands.** Deep sleep means it can't hear MQTT commands. Options: (a) wake → publish → stay awake ~20 s listening → sleep, (b) agent publishes a *retained* command that the ESP32 reads on wake, (c) stay always-on while on battery. Which one?
2. **Valve & pressure.** 7 ft gives ≈0.21 bar, and many ½" 12V valves list ~0.2 bar as the *minimum* working pressure. Do I want a fallback (raise the stand to ~9 ft, or switch to a small 12V submersible pump)? Also confirm a **flyback diode** across the valve coil and the correct relay wiring.
3. **Cycle timing.** Is 10 min between readings and 15 min verification delay right for my soil, or make them config values?
4. **Calibration.** How do I record "dry air" and "in water" raw values for the soil sensor, and where is the calibration stored?

**Batch 2 — Agent behaviour**
5. **Who decides?** Recommended: the **LLM decides inside hard limits enforced by code** (max seconds per watering, minimum hours between waterings, max waterings per day, never water if drum LOW). Confirm limits and values.
6. **LLM details.** Which Groq model, JSON schema for the answer, timeout (20 s proposed), retry count, and how the Gemini fallback switches in.
7. **Weather.** What latitude/longitude should I use for the tomato field? (Do not assume.) How is rain in the next 3 h used?
8. **Manual override & kill switch.** Should the dashboard have "water now", "pause automation", "close valve now"?

**Batch 3 — Software choices**
9. **Language/tooling.** ESP32 firmware in **Arduino C++ (PlatformIO in VS Code)** or **MicroPython**? Recommended for a beginner: tell me the trade-offs and pick one. Python version on the Pi?
10. **Backend.** Flask or FastAPI? WebSocket or simple polling for live updates?
11. **Notifications.** PWA push, Telegram bot, or just the dashboard? (I mentioned a small Android app — confirm PWA-first is acceptable.)
12. **Dashboard content.** Confirm screens: live status, history graph, decision log with LLM reasoning, alerts, override buttons.
13. **Auth.** Is "no login, only on my hotspot" acceptable for the POC?

**Batch 4 — Project mechanics**
14. **Repo layout.** Suggested: `/agent`, `/dashboard`, `/firmware`, `/simulator`, `/docs`, `/deploy`. OK?
15. **How code reaches the Pi** (git pull on the Pi, `scp`, or `rsync`)? Remember I can't run scripts on your behalf, so give me exact commands.
16. **Testing.** Unit tests for the guardrail layer + decision parser, a replayable simulator, dry-run mode. What else is worth it for a POC?
17. **Networking.** `farmhub.local` may not resolve on the ESP32 and the hotspot may change IPs. Static IP, DHCP reservation, or hard-coded fallback IP?
18. **Data retention** in SQLite (e.g. keep 90 days?) and log rotation.

If you think a question is missing — for example electrical safety around mains/12V, battery protection, waterproofing — **ask it**.

---

# 8. WHAT I EXPECT FROM YOU, IN ORDER

1. Reply with **Batch 1 of questions only** (with your recommended defaults). Nothing else.
2. Wait for my answers. Then ask the next batch, until you have enough.
3. Produce the **Implementation Plan artifact** (stages, files, risks, test steps, what I must do physically per stage).
4. **Stop and wait** for `APPROVED: <stage>`.

**Start now with Stage 0. Do not write any code or create any files yet.**
