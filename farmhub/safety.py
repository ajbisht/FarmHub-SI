"""Deterministic Safety Guardrail Engine for FarmHub AI.

Ensures that physical hardware rules and biological cooldowns are NEVER bypassed
by probabilistic LLM recommendations or anomalous cloud commands.
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class SafetyVerdict:
    allowed: bool
    reason: str
    clamped_duration_sec: int
    rule_triggered: Optional[str] = None

class DeterministicSafetyGuardrail:
    def __init__(self, max_duration_sec: int = 30, cooldown_sec: int = 7200):
        self.max_duration_sec = max_duration_sec
        self.cooldown_sec = cooldown_sec

    def evaluate(
        self,
        proposed_action: str,
        proposed_duration_sec: int,
        telemetry: Dict[str, Any],
        crop_config: Dict[str, Any]
    ) -> SafetyVerdict:
        """Evaluate a proposed watering action against physical hardware and crop safety rules."""
        
        # If the proposal is not to water, it is safe by default
        if proposed_action != "WATER":
            return SafetyVerdict(
                allowed=True,
                reason="No watering requested.",
                clamped_duration_sec=0
            )

        # 1. HARD HARDWARE INTERLOCK: Reservoir Dry
        if not telemetry.get("reservoir_level_ok", True):
            return SafetyVerdict(
                allowed=False,
                reason="BLOCKED: Water reservoir is empty. Holding off to protect pump.",
                clamped_duration_sec=0,
                rule_triggered="RESERVOIR_EMPTY_CUTOFF"
            )

        # 2. HARD HARDWARE INTERLOCK: Sensor Disconnect or Out of Bounds
        moisture = telemetry.get("soil_moisture_vwc_pct", 0.0)
        if moisture < 0.0 or telemetry.get("soil_raw_adc", 0) > 4050:
            return SafetyVerdict(
                allowed=False,
                reason="BLOCKED: Soil sensor disconnected or cable fault detected.",
                clamped_duration_sec=0,
                rule_triggered="SENSOR_FAULT"
            )

        # 3. CLOSED-LOOP INTERLOCK: Delivery Fault (Detached pipe or pump dry)
        if telemetry.get("delivery_fault", False):
            return SafetyVerdict(
                allowed=False,
                reason="BLOCKED: Previous watering did not raise soil moisture. Check tube and pump.",
                clamped_duration_sec=0,
                rule_triggered="DELIVERY_FAULT"
            )

        # 4. HYDRAULIC COOLDOWN INTERLOCK: Mandatory 2-Hour Lockout
        cooldown_remaining = telemetry.get("cooldown_remaining_sec", 0)
        if cooldown_remaining > 0:
            rem_min = int(cooldown_remaining / 60)
            return SafetyVerdict(
                allowed=False,
                reason=f"BLOCKED: Cooldown active ({rem_min}m remaining). Allowing water to percolate.",
                clamped_duration_sec=0,
                rule_triggered="COOLDOWN_ACTIVE"
            )

        # 5. CROP THRESHOLD CHECK: Is soil already moist?
        target_max = crop_config.get("target_max", 55.0)
        if moisture >= target_max:
            return SafetyVerdict(
                allowed=False,
                reason=f"BLOCKED: Soil is optimal at {moisture:.0f}% (target ceiling: {target_max}%). No water needed.",
                clamped_duration_sec=0,
                rule_triggered="CROP_TARGET_MET"
            )

        # 6. DURATION CLAMPING: Enforce 30s hard ceiling
        safe_duration = min(proposed_duration_sec, self.max_duration_sec)
        if safe_duration <= 0:
            safe_duration = crop_config.get("watering_duration_sec", 20)
        safe_duration = min(safe_duration, self.max_duration_sec)

        return SafetyVerdict(
            allowed=True,
            reason=f"APPROVED: Soil at {moisture:.0f}% requires irrigation. Safe to water for {safe_duration}s.",
            clamped_duration_sec=safe_duration,
            rule_triggered="SAFETY_PASSED"
        )
