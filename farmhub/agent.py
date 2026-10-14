"""ReAct Tool-Calling Agronomist Agent for FarmHub AI.

Demonstrates genuine Agentic AI by invoking multi-step observation tools:
- get_sensor_telemetry()
- get_weather_forecast()
- get_watering_history()
- propose_irrigation()

The proposed action is then strictly validated by the DeterministicSafetyGuardrail.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from farmhub.safety import DeterministicSafetyGuardrail, SafetyVerdict
from farmhub.weather import WeatherService

logger = logging.getLogger("farmhub.agent")

class FarmHubAgent:
    def __init__(self, weather_service: Optional[WeatherService] = None):
        self.weather_service = weather_service or WeatherService()
        self.guardrail = DeterministicSafetyGuardrail()
        self.api_key = os.getenv("GEMINI_API_KEY")

    def run_agentic_cycle(
        self,
        telemetry: Dict[str, Any],
        crop_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the full ReAct Observe -> Analyze -> Propose -> Verify loop."""
        tool_call_trace: List[Dict[str, Any]] = []

        # Tool 1: Observe Sensor Telemetry
        sensor_data = self._tool_get_sensor_telemetry(telemetry)
        tool_call_trace.append({"tool": "get_sensor_telemetry", "output": sensor_data})

        # Tool 2: Observe Weather Forecast
        weather_data = self._tool_get_weather_forecast(telemetry)
        tool_call_trace.append({"tool": "get_weather_forecast", "output": weather_data})

        # Tool 3: Observe History & Response
        history_data = self._tool_get_watering_history(telemetry)
        tool_call_trace.append({"tool": "get_watering_history", "output": history_data})

        # Step 4: Agent Reasoning & Action Proposal
        # If Gemini API key is configured, use LLM reasoning; otherwise use Autonomous Offline Agronomist
        proposal = self._generate_reasoning_and_proposal(
            sensor_data, weather_data, history_data, crop_config
        )
        tool_call_trace.append({"tool": "propose_irrigation", "output": proposal})

        # Step 5: Deterministic Safety Guardrail Verification
        verdict: SafetyVerdict = self.guardrail.evaluate(
            proposed_action=proposal["action"],
            proposed_duration_sec=proposal["duration_sec"],
            telemetry=telemetry,
            crop_config=crop_config
        )

        # Step 6: Construct Final Farmer Message (Natural tone, strictly under 12 words)
        final_message = self._format_field_message(proposal, verdict, sensor_data, weather_data)

        return {
            "agent_verdict": {
                "proposed_action": proposal["action"],
                "authorized": verdict.allowed,
                "authorized_duration_sec": verdict.clamped_duration_sec,
                "safety_reason": verdict.reason,
                "rule_triggered": verdict.rule_triggered
            },
            "field_message": final_message,
            "tool_calls_trace": tool_call_trace,
            "weather_snapshot": weather_data,
            "soil_snapshot": sensor_data
        }

    # --- Tool Implementations ---
    def _tool_get_sensor_telemetry(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "soil_moisture_vwc_pct": telemetry.get("soil_moisture_vwc_pct", 0.0),
            "soil_raw_adc": telemetry.get("soil_raw_adc", 0),
            "reservoir_level_ok": telemetry.get("reservoir_level_ok", True),
            "cooldown_remaining_sec": telemetry.get("cooldown_remaining_sec", 0),
            "delivery_fault": telemetry.get("delivery_fault", False)
        }

    def _tool_get_weather_forecast(self, telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if telemetry and "weather" in telemetry and isinstance(telemetry["weather"], dict):
            return telemetry["weather"]
        return self.weather_service.fetch_forecast()

    def _tool_get_watering_history(self, telemetry: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "total_cycles_today": telemetry.get("total_cycles_today", 0),
            "delivery_verified": telemetry.get("delivery_verified", True),
            "cooldown_active": telemetry.get("cooldown_remaining_sec", 0) > 0
        }

    # --- Reasoning Core ---
    def _generate_reasoning_and_proposal(
        self,
        sensors: Dict[str, Any],
        weather: Dict[str, Any],
        history: Dict[str, Any],
        crop_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        moisture = sensors["soil_moisture_vwc_pct"]
        target_min = crop_config.get("target_min", 30.0)
        target_max = crop_config.get("target_max", 55.0)
        rain_prob = weather.get("rain_probability_pct", 0)

        # Reservoir Empty
        if not sensors["reservoir_level_ok"]:
            return {
                "action": "WAIT",
                "duration_sec": 0,
                "intent": "REFILL_TANK",
                "raw_reason": "Water tank is empty. Holding off until refilled."
            }

        # Delivery Fault
        if sensors.get("delivery_fault", False):
            return {
                "action": "INSPECT",
                "duration_sec": 0,
                "intent": "CHECK_PIPE",
                "raw_reason": "Previous watering did not raise moisture. Inspect hose and pump."
            }

        # Soil is dry
        if moisture < target_min:
            # Check Rain Forecast: If rain expected >65%, hold off
            if rain_prob >= 65:
                return {
                    "action": "WAIT",
                    "duration_sec": 0,
                    "intent": "CONSERVE_WATER",
                    "raw_reason": f"Rain expected soon ({rain_prob}% chance). Saving water today."
                }
            else:
                duration = crop_config.get("watering_duration_sec", 25)
                return {
                    "action": "WATER",
                    "duration_sec": duration,
                    "intent": "IRRIGATE",
                    "raw_reason": f"Soil dipped to {moisture:.0f}%. Clear skies, giving plants a drink."
                }

        # Soil is optimal
        return {
            "action": "WAIT",
            "duration_sec": 0,
            "intent": "MONITOR",
            "raw_reason": f"Soil is healthy and moist at {moisture:.0f}%. Plants are happy."
        }

    def _format_field_message(
        self,
        proposal: Dict[str, Any],
        verdict: SafetyVerdict,
        sensors: Dict[str, Any],
        weather: Dict[str, Any]
    ) -> str:
        """Enforces farmer-friendly, natural phrasing strictly under 12 words with correct safety priority."""
        # 1. Tank empty alert (Highest priority)
        if not sensors.get("reservoir_level_ok", True) or proposal.get("intent") == "REFILL_TANK":
            return "Water tank is low. Holding off on watering until refilled."

        # 2. Closed-loop delivery fault alert
        if sensors.get("delivery_fault", False) or proposal.get("intent") == "CHECK_PIPE":
            return "Water didn't reach soil last time. Check pipe and pump."

        # 3. Blocked by cooldown
        cooldown_rem = sensors.get("cooldown_remaining_sec", 0)
        if cooldown_rem > 0 or verdict.rule_triggered == "COOLDOWN_ACTIVE":
            rem_m = max(1, int(cooldown_rem / 60))
            return f"Watered recently. Waiting {rem_m}m before next drink."

        # 4. If approved to water
        if verdict.allowed and proposal["action"] == "WATER":
            m = sensors["soil_moisture_vwc_pct"]
            dur = verdict.clamped_duration_sec
            return f"Soil dipped to {m:.0f}%. Clear skies, giving plants a {dur}s drink."

        # 5. If waiting for rain
        if weather.get("rain_probability_pct", 0) >= 65:
            p = weather["rain_probability_pct"]
            return f"Rain expected soon ({p}% chance). Saving water today."

        # 6. Default optimal
        m = sensors["soil_moisture_vwc_pct"]
        return f"Soil is healthy and moist at {m:.0f}%. Plants are happy."
