import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import httpx
from agent.config import config
from agent.weather import WeatherReport

logger = logging.getLogger("LLMClient")


@dataclass
class LLMDecision:
    action: str              # 'WATER' or 'SKIP'
    duration_sec: int        # Suggested runtime in seconds
    reasoning: str          # Plain English explanation for dashboard
    model_name: str          # Model that generated the decision


SYSTEM_PROMPT = """You are an expert autonomous agricultural AI agent managing irrigation for 5 healthy tomato plants in a garden bed.
Your goal is to optimize tomato plant health, fruit development, and water conservation.

INPUT DATA PROVIDED TO YOU:
- Current soil moisture percentage (0% to 100%, ideal target for tomatoes is 40% to 65%)
- Drum water reservoir level (OK or LOW)
- Current local temperature, humidity, and weather conditions
- Next 3-hour precipitation probability
- Recent soil moisture trends (last 24 hours)

RULES FOR YOUR DECISION:
1. If soil moisture is low (< 35%) and no rain is expected, recommend WATER with appropriate duration (typically 25 to 40 seconds).
2. If rain is expected in the next 3 hours (> 50% probability), prefer SKIP to conserve water unless soil is critically dry (< 20%).
3. If soil moisture is already adequate (> 45%), recommend SKIP.
4. If drum water level is LOW, you MUST recommend SKIP to protect the pump.

OUTPUT FORMAT:
You MUST respond ONLY with a valid JSON object matching this exact schema:
{
  "action": "WATER" or "SKIP",
  "duration_sec": <integer between 10 and 45 if action is WATER, otherwise 0>,
  "reasoning": "<clear, concise 1-2 sentence explanation of why you made this decision>"
}
"""


class LLMClient:
    """Interacts with Groq (Primary) and Gemini Flash (Fallback) to decide irrigation actions.
    Includes a deterministic fallback when offline or when API keys are not yet configured.
    """

    def __init__(self):
        self.groq_key = config.groq_api_key
        self.groq_model = config.groq_model
        self.gemini_key = config.gemini_api_key

    def decide(
        self,
        current_moisture_pct: float,
        drum_level: str,
        weather: WeatherReport,
        recent_history: List[Dict[str, Any]],
    ) -> LLMDecision:
        """Asks the LLM whether to water, falling back gracefully if needed."""
        user_prompt = self._build_prompt(current_moisture_pct, drum_level, weather, recent_history)

        # 1. Try Groq (Primary)
        if self.groq_key and not self.groq_key.startswith("your_"):
            decision = self._call_groq(user_prompt)
            if decision:
                return decision

        # 2. Try Gemini Flash (Fallback)
        if self.gemini_key and not self.gemini_key.startswith("your_"):
            logger.info("Attempting Gemini Flash fallback...")
            decision = self._call_gemini(user_prompt)
            if decision:
                return decision

        # 3. Deterministic Local Agronomy Rule Fallback (Offline / No API Key)
        logger.info("Using local agronomy rule engine (Offline/No API key mode).")
        return self._local_rule_fallback(current_moisture_pct, drum_level, weather)

    def _build_prompt(
        self,
        moisture: float,
        drum: str,
        weather: WeatherReport,
        history: List[Dict[str, Any]],
    ) -> str:
        history_summary = "No previous history yet."
        if history:
            pts = [f"{row.get('moisture_pct', '?')}%" for row in history[-6:]]
            history_summary = "Recent moisture readings: " + " -> ".join(pts)

        return f"""CURRENT FIELD OBSERVATIONS:
- Soil Moisture: {moisture:.1f}%
- Drum Reservoir Status: {drum}
- Weather: {weather.temp_c}°C, {weather.humidity_pct}% humidity, {weather.description}
- Rain Expected (Next 3h): {'YES' if weather.rain_expected_next_3h else 'NO'} ({weather.rain_probability_pct}% chance)
- Moisture Trend: {history_summary}

Determine whether to WATER or SKIP and return your JSON response."""

    def _call_groq(self, prompt: str) -> Optional[LLMDecision]:
        """Calls Groq free tier with JSON response format."""
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.groq_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.groq_model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                return LLMDecision(
                    action=parsed.get("action", "SKIP").upper(),
                    duration_sec=int(parsed.get("duration_sec", 0)),
                    reasoning=parsed.get("reasoning", "Decided by Groq"),
                    model_name=f"Groq ({self.groq_model})",
                )
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            return None

    def _call_gemini(self, prompt: str) -> Optional[LLMDecision]:
        """Calls Gemini 1.5 Flash fallback."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}
                ],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
            }
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)

                return LLMDecision(
                    action=parsed.get("action", "SKIP").upper(),
                    duration_sec=int(parsed.get("duration_sec", 0)),
                    reasoning=parsed.get("reasoning", "Decided by Gemini Flash"),
                    model_name="Gemini 1.5 Flash",
                )
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            return None

    def _local_rule_fallback(
        self, moisture: float, drum: str, weather: WeatherReport
    ) -> LLMDecision:
        """Deterministic local decision logic when no cloud LLM is reachable."""
        if drum == "LOW":
            return LLMDecision(
                action="SKIP",
                duration_sec=0,
                reasoning="Water reservoir is LOW. Irrigation paused to prevent pump damage.",
                model_name="Local Agronomy Engine (Offline)",
            )

        if moisture < 35.0:
            if weather.rain_expected_next_3h and moisture > 22.0:
                return LLMDecision(
                    action="SKIP",
                    duration_sec=0,
                    reasoning=f"Soil moisture is {moisture:.1f}%, but rain is forecasted ({weather.rain_probability_pct}% chance). Conserving water.",
                    model_name="Local Agronomy Engine (Offline)",
                )
            else:
                return LLMDecision(
                    action="WATER",
                    duration_sec=30,
                    reasoning=f"Soil moisture is dry ({moisture:.1f}% < target 45%). Irrigating 5 tomato plants for 30s.",
                    model_name="Local Agronomy Engine (Offline)",
                )
        else:
            return LLMDecision(
                action="SKIP",
                duration_sec=0,
                reasoning=f"Soil moisture is optimal ({moisture:.1f}%). No additional water needed.",
                model_name="Local Agronomy Engine (Offline)",
            )
