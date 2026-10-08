import json
import logging
import ssl
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import httpx
from agent.config import config
from agent.weather import WeatherReport

logger = logging.getLogger("LLMClient")


def get_ssl_context():
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        return ctx
    except Exception:
        return True


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
        self.provider = config.llm_provider
        self.groq_key = config.groq_api_key
        self.groq_model = config.groq_model
        self.openai_key = config.openai_api_key
        self.openai_model = config.openai_model
        self.anthropic_key = config.anthropic_api_key
        self.anthropic_model = config.anthropic_model
        self.gemini_key = config.gemini_api_key
        self.gemini_model = config.gemini_model
        self.ollama_base = config.ollama_base_url
        self.ollama_model = config.ollama_model

    def decide(
        self,
        current_moisture_pct: float,
        drum_level: str,
        weather: WeatherReport,
        recent_history: List[Dict[str, Any]],
    ) -> LLMDecision:
        """Asks the configured LLM whether to water, falling back gracefully if needed."""
        user_prompt = self._build_prompt(current_moisture_pct, drum_level, weather, recent_history)

        decision: Optional[LLMDecision] = None

        # 1. Primary provider based on LLM_PROVIDER in .env
        if self.provider == "openai" and self.openai_key and not self.openai_key.startswith("your_"):
            decision = self._call_openai(user_prompt)
        elif self.provider == "anthropic" and self.anthropic_key and not self.anthropic_key.startswith("your_"):
            decision = self._call_anthropic(user_prompt)
        elif self.provider == "gemini" and self.gemini_key and not self.gemini_key.startswith("your_"):
            decision = self._call_gemini(user_prompt)
        elif self.provider == "ollama":
            decision = self._call_ollama(user_prompt)
        elif self.provider == "groq" and self.groq_key and not self.groq_key.startswith("your_"):
            decision = self._call_groq(user_prompt)

        if decision:
            return decision

        # 2. Automatic Fallbacks if primary was unavailable
        if self.provider != "groq" and self.groq_key and not self.groq_key.startswith("your_"):
            logger.info("Falling back to Groq...")
            decision = self._call_groq(user_prompt)
            if decision:
                return decision

        if self.provider != "gemini" and self.gemini_key and not self.gemini_key.startswith("your_"):
            logger.info("Falling back to Gemini Flash...")
            decision = self._call_gemini(user_prompt)
            if decision:
                return decision

        # 3. Deterministic Local Agronomy Rule Fallback (Offline / Zero API Keys)
        logger.info("Using local agronomy rule engine (Offline/Deterministic mode).")
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
        """Calls Groq free tier with JSON response format and resilient model fallback."""
        candidate_models = [
            self.groq_model,
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ]
        models_to_try = [m for i, m in enumerate(candidate_models) if m and m not in candidate_models[:i]]

        for model in models_to_try:
            try:
                with httpx.Client(timeout=20.0, verify=get_ssl_context()) as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.groq_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": prompt},
                            ],
                            "temperature": 0.1,
                            "response_format": {"type": "json_object"},
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data["choices"][0]["message"]["content"]
                        parsed = json.loads(content)

                        return LLMDecision(
                            action=parsed.get("action", "SKIP").upper(),
                            duration_sec=int(parsed.get("duration_sec", 0)),
                            reasoning=parsed.get("reasoning", "Decided by Groq"),
                            model_name=f"Groq ({model})",
                        )
                    else:
                        logger.warning(f"Groq model '{model}' returned HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Groq model '{model}' failed: {e}")

        return None

    def _call_openai(self, prompt: str) -> Optional[LLMDecision]:
        """Calls OpenAI Chat Completions API with JSON response format."""
        try:
            with httpx.Client(timeout=20.0, verify=get_ssl_context()) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.openai_model,
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
                    reasoning=parsed.get("reasoning", "Decided by OpenAI"),
                    model_name=f"OpenAI ({self.openai_model})",
                )
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            return None

    def _call_anthropic(self, prompt: str) -> Optional[LLMDecision]:
        """Calls Anthropic Messages API."""
        try:
            with httpx.Client(timeout=25.0, verify=get_ssl_context()) as client:
                resp = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.anthropic_model,
                        "max_tokens": 1024,
                        "system": SYSTEM_PROMPT,
                        "messages": [
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["content"][0]["text"]
                clean_json = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                parsed = json.loads(clean_json)

                return LLMDecision(
                    action=parsed.get("action", "SKIP").upper(),
                    duration_sec=int(parsed.get("duration_sec", 0)),
                    reasoning=parsed.get("reasoning", "Decided by Anthropic"),
                    model_name=f"Anthropic ({self.anthropic_model})",
                )
        except Exception as e:
            logger.error(f"Anthropic API call failed: {e}")
            return None

    def _call_ollama(self, prompt: str) -> Optional[LLMDecision]:
        """Calls local Ollama server via its OpenAI-compatible endpoint."""
        try:
            url = f"{self.ollama_base.rstrip('/')}/v1/chat/completions"
            with httpx.Client(timeout=30.0, verify=get_ssl_context()) as client:
                resp = client.post(
                    url,
                    json={
                        "model": self.ollama_model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                clean_json = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                parsed = json.loads(clean_json)

                return LLMDecision(
                    action=parsed.get("action", "SKIP").upper(),
                    duration_sec=int(parsed.get("duration_sec", 0)),
                    reasoning=parsed.get("reasoning", "Decided by local Ollama"),
                    model_name=f"Ollama ({self.ollama_model})",
                )
        except Exception as e:
            logger.error(f"Ollama call failed at {self.ollama_base}: {e}")
            return None

    def _call_gemini(self, prompt: str) -> Optional[LLMDecision]:
        """Calls Gemini Flash API."""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}]}
                ],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
            }
            with httpx.Client(timeout=20.0, verify=get_ssl_context()) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(raw_text)

                return LLMDecision(
                    action=parsed.get("action", "SKIP").upper(),
                    duration_sec=int(parsed.get("duration_sec", 0)),
                    reasoning=parsed.get("reasoning", "Decided by Gemini"),
                    model_name=f"Gemini ({self.gemini_model})",
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


if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("[AgriAgent] Standalone LLM Provider Diagnostic Test")
    print("=" * 65)
    print(f"Active Provider (from .env): {config.llm_provider.upper()}")

    client = LLMClient()
    mock_weather = WeatherReport(
        temp_c=31.5,
        humidity_pct=42,
        rain_expected_next_3h=False,
        rain_probability_pct=5,
        description="Clear sky, sunny",
        is_live_data=False,
    )

    print("\nTesting dry soil scenario: Soil 26.5%, Drum OK, 31.5 C Sunny...")
    decision = client.decide(
        current_moisture_pct=26.5,
        drum_level="OK",
        weather=mock_weather,
        recent_history=[{"moisture_pct": 32.0}, {"moisture_pct": 29.1}, {"moisture_pct": 26.5}],
    )

    print("\n--- LLM Decision Result ---")
    print(f"- Action:      {decision.action}")
    print(f"- Duration:    {decision.duration_sec} seconds")
    print(f"- Engine Used: {decision.model_name}")
    print(f"- Reasoning:   {decision.reasoning}")
    print("=" * 65 + "\n")
