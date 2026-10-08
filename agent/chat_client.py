import json
import logging
import ssl
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import httpx

from agent.config import config
from agent.weather import WeatherReport

logger = logging.getLogger("ChatAgent")


def get_ssl_context():
    try:
        ctx = ssl.create_default_context()
        ctx.load_default_certs()
        return ctx
    except Exception:
        return True


AGRONOMIST_SYSTEM_PROMPT = """You are FarmHub's dedicated Agronomist & Automation AI Assistant.
You oversee an autonomous drip irrigation system for 5 healthy tomato plants in a raised bed garden in Ghaziabad, India.
Your role is to answer questions from the farm owner (Ajay) warmly, concisely, and with deep agronomic and technical expertise.

YOU HAVE REAL-TIME ACCESS TO THE FARM'S LIVE SENSORS, WEATHER, AND IRRIGATION RECORDS:
{context_block}

GUIDELINES FOR YOUR RESPONSES:
1. Always base your answers on the REAL-TIME DATA provided above (quote the exact moisture %, battery voltage, drum status, or weather when relevant).
2. For tomato care advice (watering thresholds, blossom end rot, pruning, flowering, fruiting, soil nutrients), give practical, actionable horticultural recommendations.
3. If asked why a watering happened or was skipped, cite the AI reasoning and guardrail policy in the history.
4. If battery < 11.0V or drum is LOW, remind the user about safety lockouts.
5. Keep your tone encouraging, professional, and concise (2-4 clear paragraphs or bullet points). Use formatting like bold text and bullet points for readability. Avoid generic greetings every time.
"""


class FarmChatAgent:
    """Conversational AI agent that responds to user inquiries using live telemetry,

    recent irrigation history, and real-time weather context.
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

    def _assemble_context(
        self,
        telemetry: Dict[str, Any],
        weather: Optional[WeatherReport],
        decisions: List[Dict[str, Any]],
        waterings_24h: int,
    ) -> str:
        """Formats live sensors, weather, and history into a readable context block."""
        moisture = telemetry.get("moisture_pct", 0.0)
        drum = telemetry.get("drum_level", "OK")
        battery = telemetry.get("battery_v", 12.2)
        pump = telemetry.get("pump_state", "IDLE")
        raw_adc = telemetry.get("raw_adc", "--")
        paused = "YES (Safety Pause)" if telemetry.get("automation_paused") else "NO (Active)"

        weather_str = "Weather data unavailable"
        if weather:
            weather_str = (
                f"{weather.temp_c}°C, {weather.humidity_pct}% humidity, {weather.description}. "
                f"Rain in next 3h: {'YES (' + str(weather.rain_probability_pct) + '%)' if weather.rain_expected_next_3h else 'NO'}"
            )

        decisions_summary = "No recent AI decisions recorded yet."
        if decisions:
            recent_lines = []
            for d in decisions[:4]:
                action = d.get("action", "UNKNOWN")
                ts = d.get("timestamp", "")
                reason = d.get("reasoning", "")
                model = d.get("model_used", "AI")
                recent_lines.append(f"- [{ts}] {action} via {model}: {reason}")
            decisions_summary = "\n".join(recent_lines)

        return f"""[CURRENT TELEMETRY & STATUS]
- Soil Moisture: {moisture:.1f}% (Ideal tomato target: 40% - 65%)
- Water Drum Reservoir: {drum} (Float Switch)
- Field Battery: {battery:.1f}V (3S Li-ion; cutoff is 11.0V)
- Pump Actuator State: {pump}
- Raw Capacitive ADC: {raw_adc}
- Automation Suspended: {paused}
- Waterings in last 24h: {waterings_24h} (Daily limit: 4)

[LIVE LOCAL WEATHER - {config.location_name}]
- {weather_str}

[RECENT DECISION HISTORY]
{decisions_summary}
"""

    def chat(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        telemetry: Optional[Dict[str, Any]] = None,
        weather: Optional[WeatherReport] = None,
        decisions: Optional[List[Dict[str, Any]]] = None,
        waterings_24h: int = 0,
    ) -> str:
        """Generates a conversational response using live context and configured LLM."""
        telemetry = telemetry or {}
        decisions = decisions or []
        history = conversation_history or []

        context_block = self._assemble_context(telemetry, weather, decisions, waterings_24h)
        system_content = AGRONOMIST_SYSTEM_PROMPT.format(context_block=context_block)

        # Build message history for LLM API
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_content}]
        for turn in history[-6:]:  # Keep last 3 exchanges for context window efficiency
            role = "user" if turn.get("role") == "user" else "assistant"
            content = turn.get("content", "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        # 1. Primary provider
        reply: Optional[str] = None
        if self.provider == "openai" and self.openai_key and not self.openai_key.startswith("your_"):
            reply = self._call_openai(messages)
        elif self.provider == "anthropic" and self.anthropic_key and not self.anthropic_key.startswith("your_"):
            reply = self._call_anthropic(system_content, history, user_message)
        elif self.provider == "gemini" and self.gemini_key and not self.gemini_key.startswith("your_"):
            reply = self._call_gemini(system_content, user_message)
        elif self.provider == "ollama":
            reply = self._call_ollama(messages)
        elif self.provider == "groq" and self.groq_key and not self.groq_key.startswith("your_"):
            reply = self._call_groq(messages)

        if reply:
            return reply

        # 2. Fallbacks if primary provider failed or unconfigured
        if self.provider != "groq" and self.groq_key and not self.groq_key.startswith("your_"):
            logger.info("Falling back to Groq for chat...")
            reply = self._call_groq(messages)
            if reply:
                return reply

        if self.provider != "gemini" and self.gemini_key and not self.gemini_key.startswith("your_"):
            logger.info("Falling back to Gemini Flash for chat...")
            reply = self._call_gemini(system_content, user_message)
            if reply:
                return reply

        # 3. Intelligent Local Fallback when all LLM calls fail or offline
        logger.info("Using intelligent local agronomy fallback response.")
        return self._local_fallback(user_message, telemetry, weather, decisions)

    def _call_groq(self, messages: List[Dict[str, str]]) -> Optional[str]:
        candidate_models = [
            self.groq_model,
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "qwen/qwen3.8-27b",
        ]
        models_to_try = [m for i, m in enumerate(candidate_models) if m and m not in candidate_models[:i]]

        for model in models_to_try:
            try:
                with httpx.Client(timeout=25.0, verify=get_ssl_context()) as client:
                    resp = client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.groq_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": messages,
                            "temperature": 0.5,
                            "max_tokens": 600,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        logger.warning(f"Groq chat model '{model}' HTTP {resp.status_code}: {resp.text}")
            except Exception as e:
                logger.error(f"Groq chat model '{model}' failed: {e}")
        return None

    def _call_openai(self, messages: List[Dict[str, str]]) -> Optional[str]:
        try:
            with httpx.Client(timeout=25.0, verify=get_ssl_context()) as client:
                resp = client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.openai_model,
                        "messages": messages,
                        "temperature": 0.5,
                        "max_tokens": 600,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
        return None

    def _call_anthropic(self, system_prompt: str, history: List[Dict[str, str]], user_msg: str) -> Optional[str]:
        try:
            msgs = []
            for turn in history[-6:]:
                role = "user" if turn.get("role") == "user" else "assistant"
                msgs.append({"role": role, "content": turn.get("content", "")})
            msgs.append({"role": "user", "content": user_msg})

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
                        "max_tokens": 600,
                        "system": system_prompt,
                        "messages": msgs,
                        "temperature": 0.5,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["content"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Anthropic chat failed: {e}")
        return None

    def _call_gemini(self, system_prompt: str, user_msg: str) -> Optional[str]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": f"{system_prompt}\n\nUser Question: {user_msg}"}]}
                ],
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 600},
            }
            with httpx.Client(timeout=25.0, verify=get_ssl_context()) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        return candidates[0]["content"]["parts"][0]["text"].strip()
        except Exception as e:
            logger.error(f"Gemini chat failed: {e}")
        return None

    def _call_ollama(self, messages: List[Dict[str, str]]) -> Optional[str]:
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self.ollama_base}/v1/chat/completions",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": self.ollama_model,
                        "messages": messages,
                        "temperature": 0.5,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Ollama chat failed: {e}")
        return None

    def _local_fallback(
        self,
        query: str,
        telemetry: Dict[str, Any],
        weather: Optional[WeatherReport],
        decisions: List[Dict[str, Any]],
    ) -> str:
        """Deterministic context-aware answer when LLM is unreachable."""
        m = telemetry.get("moisture_pct", 0.0)
        drum = telemetry.get("drum_level", "OK")
        bat = telemetry.get("battery_v", 12.0)
        q = query.lower()

        weather_desc = f"{weather.temp_c}°C {weather.description}" if weather else "Clear"

        if "health" in q or "plant" in q or "how" in q and "doing" in q:
            status = "healthy and well-hydrated" if m >= 40 else "a bit thirsty"
            return (
                f"🌱 **Plant Health Summary**:\n\n"
                f"Your 5 tomato plants look {status}. Soil moisture is currently **{m:.1f}%** "
                f"(target range is 40% - 65%). Local conditions in Ghaziabad are **{weather_desc}**.\n\n"
                f"• Reservoir: **{drum}**\n"
                f"• Field Battery: **{bat:.1f}V**"
            )
        elif "why" in q or "last" in q or "decision" in q:
            last_dec = decisions[0] if decisions else None
            if last_dec:
                return (
                    f"💧 **Latest Irrigation Decision**:\n\n"
                    f"• **Action**: `{last_dec.get('action')}`\n"
                    f"• **Model**: `{last_dec.get('model_used')}`\n"
                    f"• **Reasoning**: {last_dec.get('reasoning')}\n"
                    f"• Current Soil Moisture: **{m:.1f}%**"
                )
            return f"💧 No irrigation decisions have been logged yet. Current soil moisture is **{m:.1f}%**."
        elif "weather" in q or "rain" in q:
            rain_info = f"Rain chance in 3h: {weather.rain_probability_pct}%" if weather else "No rain forecast available."
            return f"🌤️ **Local Weather ({config.location_name})**:\n\n• Condition: {weather_desc}\n• {rain_info}"
        else:
            return (
                f"🌿 **FarmHub Telemetry Update**:\n\n"
                f"• **Soil Moisture**: {m:.1f}%\n"
                f"• **Drum Reservoir**: {drum}\n"
                f"• **Battery Voltage**: {bat:.1f}V\n"
                f"• **Weather**: {weather_desc}\n\n"
                f"All systems are operating normally under automated closed-loop control."
            )
