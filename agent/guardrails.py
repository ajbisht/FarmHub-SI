import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from agent.config import config
from agent.weather import WeatherReport

logger = logging.getLogger("Guardrails")


@dataclass
class GuardrailResult:
    approved: bool
    final_action: str          # 'WATER' or 'SKIP'
    final_duration_sec: int
    reason: str
    verdict_type: str          # 'APPROVED', 'MODIFIED', 'BLOCKED'


class GuardrailEngine:
    """Enforces strict, code-level safety limits on every AI decision.
    The LLM proposes actions, but this engine has absolute veto power.
    """

    def __init__(self):
        self.max_pump_seconds = config.max_pump_seconds
        self.min_hours_gap = config.min_hours_between_waterings
        self.max_daily_waterings = config.max_waterings_per_day
        self.max_safe_moisture = config.max_safe_moisture_pct

    def evaluate(
        self,
        proposed_action: str,
        proposed_duration_sec: int,
        current_moisture_pct: float,
        drum_level: str,
        weather: WeatherReport,
        last_pump_time: Optional[datetime],
        waterings_in_last_24h: int,
        battery_v: Optional[float] = None,
        raw_adc: Optional[int] = None,
        consecutive_verification_failures: int = 0,
    ) -> GuardrailResult:
        """Evaluates an AI proposal against all hard-coded safety constraints."""

        # If LLM itself decided to SKIP, approve immediately
        if proposed_action.upper() != "WATER":
            return GuardrailResult(
                approved=True,
                final_action="SKIP",
                final_duration_sec=0,
                reason="AI decided to SKIP. Approved.",
                verdict_type="APPROVED",
            )

        # ----------------------------------------------------------------------
        # RULE 1: DRUM SAFETY (Never run pump dry)
        # ----------------------------------------------------------------------
        if drum_level.upper() == "LOW":
            logger.warning("GUARDRAIL VETO: Drum water level is LOW! Blocking pump run.")
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason="BLOCKED: Drum level is LOW. Pump cannot be operated dry.",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 2: OVERSATURATION SAFETY (Never water already wet soil)
        # ----------------------------------------------------------------------
        if current_moisture_pct >= self.max_safe_moisture:
            logger.warning(
                f"GUARDRAIL VETO: Moisture {current_moisture_pct}% >= max safe threshold ({self.max_safe_moisture}%)."
            )
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: Moisture ({current_moisture_pct}%) is already above safe limit ({self.max_safe_moisture}%).",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 3: COOLDOWN SAFETY (Prevent back-to-back watering)
        # ----------------------------------------------------------------------
        if last_pump_time:
            now_dt = datetime.now(timezone.utc)
            if last_pump_time.tzinfo is None:
                last_pump_time = last_pump_time.replace(tzinfo=timezone.utc)
            hours_since_last = (now_dt - last_pump_time).total_seconds() / 3600.0
            if hours_since_last < self.min_hours_gap:
                logger.warning(
                    f"GUARDRAIL VETO: Cooldown active. Last watering was {hours_since_last:.2f}h ago (minimum gap: {self.min_hours_gap}h)."
                )
                return GuardrailResult(
                    approved=False,
                    final_action="SKIP",
                    final_duration_sec=0,
                    reason=f"BLOCKED: Cooldown active ({hours_since_last:.1f}h since last water, required: {self.min_hours_gap}h).",
                    verdict_type="BLOCKED",
                )

        # ----------------------------------------------------------------------
        # RULE 4: DAILY WATERING CAP
        # ----------------------------------------------------------------------
        if waterings_in_last_24h >= self.max_daily_waterings:
            logger.warning(
                f"GUARDRAIL VETO: Daily cap ({self.max_daily_waterings}) reached in last 24h ({waterings_in_last_24h} waterings)."
            )
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: Daily cap reached ({waterings_in_last_24h}/{self.max_daily_waterings} runs in last 24h).",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 5: RAIN FORECAST CONSERVATION (Unless critically dry)
        # ----------------------------------------------------------------------
        if weather.rain_expected_next_3h and current_moisture_pct > 25.0:
            logger.info("GUARDRAIL VETO: Rain forecast in next 3 hours and soil is not critically dry.")
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: Rain expected in next 3h ({weather.rain_probability_pct}% chance). Soil not critically dry ({current_moisture_pct}%).",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 6: BATTERY LOW VOLTAGE CUTOFF (Li-ion 3S protection)
        # ----------------------------------------------------------------------
        if battery_v is not None and battery_v < 11.0:
            logger.warning(f"GUARDRAIL VETO: Battery voltage critically low ({battery_v:.1f}V < 11.0V).")
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: Battery voltage critically low ({battery_v:.1f}V < 11.0V). Pump locked to prevent brownout and battery damage.",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 7: SENSOR HARDWARE FAULT BOUNDS (Unplugged or Short-circuit)
        # ----------------------------------------------------------------------
        if raw_adc is not None and (raw_adc < 500 or raw_adc > 3600):
            logger.warning(f"GUARDRAIL VETO: Raw ADC ({raw_adc}) out of physical bounds (500-3600).")
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: Soil sensor raw ADC ({raw_adc}) is out of physical range (500-3600). Sensor fault or wire disconnection suspected.",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 8: CONSECUTIVE VERIFICATION ANOMALIES (Burst Pipe Lockout)
        # ----------------------------------------------------------------------
        if consecutive_verification_failures >= 2:
            logger.warning(
                f"GUARDRAIL VETO: {consecutive_verification_failures} consecutive irrigation cycles failed moisture verification."
            )
            return GuardrailResult(
                approved=False,
                final_action="SKIP",
                final_duration_sec=0,
                reason=f"BLOCKED: {consecutive_verification_failures} consecutive waterings failed moisture verification. Suspected pipe disconnect, clog, or leak.",
                verdict_type="BLOCKED",
            )

        # ----------------------------------------------------------------------
        # RULE 6: DURATION CLAMPING (Enforce safe runtime bounds)
        # ----------------------------------------------------------------------
        approved_duration = proposed_duration_sec
        verdict_type = "APPROVED"
        reason = "AI WATER recommendation approved by guardrails."

        if approved_duration > self.max_pump_seconds:
            logger.warning(
                f"GUARDRAIL CLAMP: Proposed duration {approved_duration}s exceeds maximum {self.max_pump_seconds}s. Clamping down."
            )
            approved_duration = self.max_pump_seconds
            verdict_type = "MODIFIED"
            reason = f"MODIFIED: Runtime clamped down to safe maximum of {self.max_pump_seconds}s."
        elif approved_duration < 10:
            # Minimum useful pump run
            approved_duration = 10
            verdict_type = "MODIFIED"
            reason = "MODIFIED: Runtime clamped up to minimum effective duration of 10s."

        return GuardrailResult(
            approved=True,
            final_action="WATER",
            final_duration_sec=approved_duration,
            reason=reason,
            verdict_type=verdict_type,
        )
