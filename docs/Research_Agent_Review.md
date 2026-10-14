# FarmHub POC Architecture Research Review

**Subject:** IoT + Agentic AI farm-monitoring and precision-irrigation POC  
**Prepared for:** Ajay Bisht  
**Review date:** 14 October 2026  
**Source reviewed:** `FARMHUB_SOLUTION_ARCHITECTURE_AND_REVIEW.md`

---

## 1. Executive Summary

The proposed FarmHub solution is a strong foundation for a **small, supervised proof of concept**, ideally covering one reservoir and one or two irrigation zones with reliable mains power and Wi-Fi.

Its most important architectural strength is the separation of responsibilities:

- Deterministic irrigation safety remains on the ESP32 at the edge.
- A separate ESP32-CAM handles crop imagery.
- Cloud services aggregate telemetry, weather and image information.
- An LLM converts evaluated conditions into natural-language advice.

This is the right basic direction for a rural deployment because loss of internet connectivity should not make the pump unsafe. However, the design is **not yet ready for unattended field operation**. Its major weaknesses are the absence of a truly independent hardware pump cutoff, insufficient verification of actual water delivery, outdoor construction limitations, incomplete command security, unproven soil-sensor accuracy and an AI layer that is advisory rather than genuinely agentic.

### Overall Assessment

| Area | Assessment |
|---|---|
| Basic IoT monitoring POC | Strong |
| Automated irrigation POC | Viable after safety improvements |
| Unattended operation | Not ready |
| Resilience to village connectivity issues | Partially addressed |
| Outdoor and environmental readiness | Weak |
| Agentic AI maturity | Early/advisory |
| Whole-farm scalability | Not yet demonstrated |

### Recommendation

Proceed with a limited POC, but position it as:

> **An edge-safe IoT irrigation and crop-monitoring POC with an AI agronomy and anomaly-detection assistant.**

Do not yet present it as a production-grade autonomous farm or a fully agentic solution.

---

## 2. Scope of the Proposed Solution

The reviewed architecture contains four major layers:

1. **Edge irrigation and telemetry node**
   - ESP32-WROOM controller
   - Capacitive soil-moisture sensor
   - Reservoir float switch
   - Relay and submersible pump
   - Local finite-state machine and safety timers

2. **Independent crop-vision node**
   - ESP32-CAM
   - OV2640 camera
   - Image capture and upload

3. **Cloud intelligence layer**
   - FastAPI on Google Cloud Run
   - Telemetry persistence
   - Weather forecast integration
   - LLM-generated agronomy messages

4. **Presentation and control layer**
   - Lightweight web dashboard
   - Alerts
   - Crop profiles
   - Manual irrigation controls subject to safety rules

The document estimates a core component cost of approximately **₹1,527**, excluding weatherproof enclosures, connectors, cabling, fuses, flow sensing, backup power, installation and field-hardening materials.

---

## 3. Positive Aspects

### 3.1 Correct Edge-First Safety Philosophy

The irrigation controller is designed to operate independently of cloud availability. It evaluates the float switch, soil reading, cooldown state and maximum pump duration locally.

This is a significant advantage in a village environment, where internet connectivity can fluctuate. Cloud services should enhance monitoring and decision support, not become a prerequisite for safely stopping the pump.

### 3.2 Effective Split-Node Architecture

Using separate controllers for irrigation and vision is a sound POC decision.

Benefits include:

- A camera crash does not stop irrigation.
- Pump timing is not affected by image capture or JPEG processing.
- The camera can be mounted above the canopy while the irrigation controller remains near the soil and reservoir.
- The soil sensor can use an ADC1 pin without interference from camera and Wi-Fi demands.
- Electrical load spikes from image capture are less likely to reset the irrigation controller.
- Each subsystem can be developed, tested and replaced independently.

For this POC, these advantages are more valuable than the reduction in board count offered by an all-in-one ESP32-S3 design.

### 3.3 LLM Outside the Critical Control Loop

The architecture correctly places deterministic rules before the LLM. The LLM explains the evaluated condition in natural language instead of independently deciding whether a pump-safety interlock should be bypassed.

This is the appropriate boundary for generative AI. A probabilistic model should not directly energize a pump based solely on a prompt, image or weather prediction.

### 3.4 Good Initial Failure-Mode Analysis

The design considers several realistic failures:

- Internet loss
- Empty reservoir
- Soil-sensor disconnection
- Relay failure
- Camera brownouts
- Cloud cold starts

Including failure analysis at the POC stage makes bench testing and fault-injection testing much more effective.

### 3.5 Low-Cost and Accessible Hardware

The selected components are affordable, commonly available and easy to replace. This is suitable for a learning-oriented or demonstrative deployment in a village.

The low BOM cost also permits building a spare node and testing destructive or failure conditions without placing a large investment at risk.

### 3.6 Useful Telemetry Model

The proposed telemetry includes both agricultural and device-health data:

- Raw soil ADC reading
- Converted soil-moisture percentage
- Reservoir state
- Pump state
- Time since watering
- Daily watering count
- Wi-Fi signal strength
- Reconnect count
- Uptime
- Free heap
- Firmware version

Retaining the raw ADC reading is especially useful because it supports later recalibration and troubleshooting.

### 3.7 Cloud Latency Is Decoupled from Pump Safety

The edge node does not need to wait for weather retrieval or LLM inference to complete a safe local irrigation cycle. This reduces the operational impact of Cloud Run cold starts and third-party API delays.

### 3.8 Lightweight Dashboard

A dashboard based on HTML, CSS and JavaScript is appropriate for a POC because it minimizes build and hosting complexity. Configurable crop profiles make it possible to demonstrate multiple crops without redesigning the entire application.

### 3.9 Strong Demonstration Value

The architecture demonstrates several useful concepts in one POC:

- Edge versus cloud responsibility
- Sensor telemetry
- Remote monitoring
- Actuator control
- Weather-aware policy
- Computer vision
- Natural-language explanation
- Failure handling
- Device-health monitoring

---

## 4. Negative Aspects and Risks

### 4.1 The Claimed Hardware Interlock Is Primarily Software-Based — Critical

The float switch is read through an ESP32 GPIO, after which firmware turns the relay off. This is useful, but it is not fully independent hardware protection. It still depends on the microcontroller, firmware, GPIO and switching stage working correctly.

#### Recommended improvement

Add an independent safety chain, such as:

- A float switch directly in the pump-enable or relay-coil path
- A normally-off MOSFET controlled through a hardware enable circuit
- A hardware monostable that removes pump power after a fixed maximum time
- An emergency cutoff independent of the ESP32

The current mechanism should be described as a **firmware-enforced interlock** until this change is made.

### 4.2 A Software Watchdog Cannot Stop Welded Relay Contacts — Critical

If mechanical relay contacts weld closed, changing the ESP32 GPIO state will not interrupt the pump current. The software may report that the pump is off even though it continues to run.

#### Recommended improvement

- Use a properly rated logic-level MOSFET for the small DC pump, or add an independent cutoff stage.
- Add an inline fuse.
- Measure pump current or water flow.
- Detect disagreement between commanded state and measured state.
- Raise an urgent alarm when flow continues after an OFF command.

### 4.3 Electrical Isolation Is Overstated

The design uses a common ground among the ESP32, relay and pump supply while also referring to optocoupler isolation. With a shared ground, the optocoupler may reduce signal coupling but does not provide complete galvanic isolation.

A common supply for the controllers, relay and motor also allows pump-start noise and voltage dips to affect the logic electronics.

#### Recommended improvement

- Separate the pump and logic into fused power branches.
- Use a dedicated DC/DC regulator for logic.
- Add bulk capacitance near the pump branch.
- Add local decoupling near each controller.
- Use appropriate flyback and motor-noise suppression.
- Implement a deliberate star-ground layout on a PCB or terminal board.

### 4.4 Breadboard Construction Is Unsuitable for Outdoor Deployment

A solderless breadboard and loose jumper wires are not appropriate for a humid, dusty or wet agricultural environment. Likely issues include corrosion, condensation, insects, fertilizer contamination, loose connections and accidental water exposure.

#### Recommended improvement

- Soldered perfboard or small PCB
- IP65-class enclosure
- Cable glands
- Waterproof connectors
- Strain relief
- Camera rain hood
- Fixed camera mount
- Replaceable, labelled fuse
- Conformal coating where appropriate

### 4.5 Soil-Moisture Accuracy Is Overstated

The inexpensive capacitive sensor is described as reporting volumetric water content. In practice, its raw output cannot be treated as dependable VWC without calibration for the actual soil and installation.

Measurements can vary with:

- Soil composition
- Salinity
- Compaction
- Temperature
- Sensor depth
- Probe orientation
- Manufacturing variation
- Ageing and moisture ingress

A single probe may also fail to represent conditions across a larger bed.

#### Recommended improvement

- Store raw ADC readings.
- Calibrate every sensor in the actual village soil.
- Establish dry, field-capacity and saturated reference readings.
- Use median filtering and hysteresis.
- Detect unrealistic rate-of-change.
- Use two probes per representative zone where practical.
- Validate crop thresholds through local trials rather than relying only on generic profiles.

### 4.6 No Proof That Water Was Delivered

The controller knows that it sent an ON command, but not whether:

- The pump started
- The pipe is blocked
- The hose is detached
- Water is leaking
- The pump is dry-running despite the float switch
- The expected volume reached the crop

#### Recommended improvement

Add a low-cost flow sensor, pump-current sensor or both. A closed-loop cycle should verify:

1. The pump was commanded ON.
2. Expected current or flow appeared.
3. The correct amount of water was delivered.
4. Soil moisture responded within an expected time window.

Without this feedback, the system is command-based rather than fully closed-loop.

### 4.7 Reboot and Cooldown Persistence Are Undefined

If cooldown state exists only in RAM, an ESP32 reboot could erase the lockout period and permit another watering cycle too soon.

#### Recommended improvement

Persist these values in nonvolatile storage:

- Last completed watering time
- Cooldown expiry
- Daily watering count
- Last accepted command ID
- Active crop-profile version
- Sensor calibration values
- Safety-limit configuration

After reboot, the device should reconstruct state conservatively and keep the pump off if time or state is uncertain.

### 4.8 Remote Command Security Is Incomplete

A bearer token alone does not address the complete command-security problem. The design does not clearly define:

- Per-device identity
- Command ID
- Issue and expiry times
- Sequence number or nonce
- Replay prevention
- Idempotency
- Credential rotation
- Signed firmware
- Secure OTA
- Override audit trail

A duplicate or delayed irrigation command must not start another cycle.

#### Recommended improvement

Every command should include:

```json
{
  "command_id": "unique-id",
  "device_id": "farmhub-node-01",
  "command": "IRRIGATE_CYCLE",
  "duration_seconds": 20,
  "issued_at": "timestamp",
  "expires_at": "timestamp",
  "sequence": 123,
  "requested_by": "user-or-agent",
  "signature": "cryptographic-signature"
}
```

The edge node should reject expired, duplicate, incorrectly sequenced or unauthenticated commands.

### 4.9 Rural Power and Connectivity Need Stronger Treatment

The design assumes mains power and Wi-Fi. This may work near a house but may not be sufficient for a remote plot.

#### Recommended improvement

- Measure Wi-Fi signal at every proposed node location.
- Test router failure separately from internet failure.
- Buffer telemetry locally and upload it after reconnection.
- Add a local status LED or buzzer.
- Use battery-backed 12 V power or a small UPS where necessary.
- Add surge, fuse and reverse-polarity protection.
- Consider cellular or LoRa only if dependable Wi-Fi is unavailable.

For one or two mains-powered nodes, HTTPS is adequate for the POC. MQTT becomes more valuable for multiple devices, unreliable links, battery operation or frequent downstream commands. If MQTT is selected, use a dedicated or managed broker rather than using a scale-to-zero request service as the persistent broker.

### 4.10 Computer-Vision Goals Are Too Broad

A fixed 2 MP ESP32 camera can support time-lapse images and gross anomaly detection, but reliable crop diagnosis is difficult because of:

- Changing sunlight and shadows
- Night conditions
- Rain or dust on the lens
- Plant motion
- Camera movement
- Similar symptoms caused by disease, nutrient stress, water stress or normal ageing
- Small pests that are not visible from the chosen distance

#### Appropriate POC vision goals

- Canopy-growth tracking
- Gross wilt detection
- Large yellow-area detection
- Image-quality monitoring
- Human-inspection alerts

A single image classification should not trigger irrigation or chemical treatment. Images should be captured from a fixed position and at approximately the same time of day. Human-verified labels should be retained for evaluation.

### 4.11 The AI Is Advisory, Not Yet Fully Agentic

The proposed LLM converts a small set of readings into a short natural-language message. This is useful, but it does not yet demonstrate key agentic capabilities such as:

- Multi-step planning
- Tool selection
- Historical memory
- Observation-action-verification loops
- Confidence handling
- Maintenance-task generation
- Reflection on results
- Escalation to a human

The deterministic rules make the real irrigation decision; the LLM mainly explains it. This is safer, but the solution should not overstate its current agentic maturity.

### 4.12 The Current Design Represents One Bed or Zone

One soil sensor, one pump, one reservoir and one camera are appropriate for a demonstration plot, pot, raised bed or greenhouse section. They do not represent a complete farm with different soils, elevations, crops and irrigation lines.

#### Scaling requirements

- Multiple sensor nodes
- Independently controlled valves or pumps
- Zone-specific crop profiles
- Device and zone provisioning
- Fleet health monitoring
- Secure OTA
- Per-zone water accounting
- Local gateway or long-range communication
- Prioritization when water is limited

### 4.13 Design Inconsistencies

The document should reconcile the following:

- Temperature and humidity appear in telemetry, but no environmental sensor is listed in the BOM.
- A fused pump branch is mentioned in the failure analysis, but no fuse appears in the BOM.
- The power supply is described with different current ratings in different sections.
- HTTP, MQTT, WSS and SSE are all shown without a single selected device protocol.
- Cloud Storage and Firestore are both shown without clear data ownership.
- OTA remains an open question.
- Synchronization of crop configuration between cloud and offline edge is undefined.

---

## 5. Recommended Agentic AI Architecture

The AI should remain in the cloud or gateway layer, while deterministic edge firmware retains final safety authority.

### 5.1 Recommended Agent Loop

1. **Observe**
   - Retrieve moisture trends, reservoir state, watering history, weather, images and device health.

2. **Analyse**
   - Detect abnormal trends, stale sensors, probable water stress and equipment faults.

3. **Plan**
   - Produce a structured recommendation such as:
     - `WATER`
     - `WAIT`
     - `INSPECT`
     - `REFILL_TANK`
     - `CHECK_SENSOR`
     - `CHECK_PIPE`

4. **Validate**
   - Pass the proposed action through deterministic cloud policy and edge safety rules.

5. **Approve**
   - During the POC, require human approval for AI-initiated watering.

6. **Act**
   - Send an authenticated, expiring and idempotent command.

7. **Verify**
   - Check pump current or flow and evaluate subsequent soil-moisture response.

8. **Record**
   - Store the observation, recommendation, approval, action and result.

### 5.2 Recommended Structured Agent Output

```json
{
  "recommended_action": "WAIT",
  "reason": "Rain probability is high and soil moisture is above the emergency threshold.",
  "confidence": 0.82,
  "evidence": {
    "soil_moisture_pct": 28.4,
    "rain_probability_pct": 85,
    "reservoir_ok": true,
    "hours_since_last_water": 4.2
  },
  "requires_human_approval": false,
  "recheck_after_minutes": 60
}
```

The friendly dashboard sentence can be generated from this structured object. The structured decision should remain available for audit and evaluation.

### 5.3 AI Safety Boundaries

The agent must never be allowed to:

- Bypass the empty-tank cutoff
- Exceed maximum pump duration
- Disable cooldown without an explicit, audited maintenance procedure
- Act on stale or missing sensor data
- Treat a vision result as definitive disease diagnosis
- Start repeated cycles from duplicated commands
- Change safety limits through an unvalidated natural-language instruction

---

## 6. Minimum Changes Before Field Actuation

The following changes should be treated as mandatory:

1. Replace the breadboard with a soldered board and weatherproof enclosure.
2. Add an independent low-water cutoff in the pump-enable path.
3. Use a properly rated MOSFET or independent cutoff and add a fuse.
4. Separate and decouple pump and logic power branches.
5. Add water-flow or pump-current feedback.
6. Calibrate moisture sensors in the actual soil.
7. Persist cooldown and last-watering state across reboots.
8. Add command IDs, expiry, replay protection and per-device credentials.
9. Buffer telemetry locally during connectivity loss.
10. Keep all LLM-generated actions advisory during the initial POC.

---

## 7. Recommended POC Rollout

### Phase 1 — Telemetry Only

Deploy sensors without automatic pump operation.

Measure:

- Soil-sensor stability
- Dry and wet calibration points
- Wi-Fi reliability
- Camera image quality
- Power quality
- Weather-data relevance

### Phase 2 — Supervised Irrigation

Enable pump operation only while a person is present.

Measure:

- Delivered water versus pump duration
- Pump-current signature
- Flow rate
- Moisture response after watering
- Reservoir behavior
- Electrical noise during startup and shutdown

### Phase 3 — Fault Injection

Explicitly test:

- Internet outage
- Router outage
- Cloud API outage
- Weather API failure
- Empty reservoir
- Disconnected sensor
- Sensor short to ground or supply
- ESP32 reboot during cooldown
- Duplicate command
- Expired command
- Blocked pipe
- Detached hose
- Pump failure
- Camera failure
- Power dip during motor startup
- Relay or switch failing to turn off

### Phase 4 — AI Advisory Evaluation

Let the agent generate recommendations and maintenance alerts, but compare every recommendation with a human decision.

Track:

- Correct recommendation rate
- Unsafe recommendation rate
- False alarms
- Missed faults
- Confidence calibration
- Human acceptance or rejection
- Outcome after the action

### Phase 5 — Limited Unattended Trial

Operate one irrigation zone unattended only after:

- Independent cutoff testing passes
- Electrical protection passes
- State persistence passes
- Command-security tests pass
- Water-delivery verification passes
- Alerts and offline behavior pass

---

## 8. POC Success Criteria

The POC should be considered successful only if it demonstrates measurable outcomes.

### Safety

- No pump operation with an empty reservoir
- No cycle longer than the configured maximum
- No repeated watering after reboot
- No duplicate-command actuation
- Independent cutoff successfully stops water during a simulated controller failure

### Reliability

- Telemetry is retained during an internet outage and uploaded later
- Nodes recover automatically after router and power restoration
- Camera failure does not affect irrigation
- Sensor failure is detected rather than interpreted as extreme dryness

### Agronomic Usefulness

- Calibrated moisture readings correlate with manual soil observations
- Watering causes an expected change in moisture
- Weather-aware recommendations reduce unnecessary watering without stressing the crop
- Alerts identify real maintenance needs with an acceptable false-alarm rate

### AI Quality

- Every recommendation includes evidence and confidence
- Unsafe actions are blocked by deterministic policy
- Human reviewers can trace why an action was proposed
- The system verifies the result after an approved action

---

## 9. Final Conclusion

The FarmHub architecture is a credible and educational starting point for integrating IoT, cloud services, computer vision and generative AI in a village farm-monitoring POC. Its split-node topology and edge-first control philosophy are sound.

The main gap is that software safety is being treated as if it were independent hardware safety. The solution also lacks confirmation that water was physically delivered, robust outdoor construction, complete device security, persistent safety state and locally calibrated sensing.

The AI layer should initially remain advisory. A more meaningful agentic implementation can observe historical data, plan an action, pass it through deterministic policy, request approval, execute a secure command, verify the physical result and record the outcome.

The governing principle should be:

> **AI may recommend, deterministic policy may authorize, but independent hardware must always be able to stop the water.**
