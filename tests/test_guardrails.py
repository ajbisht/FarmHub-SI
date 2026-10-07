import pytest
from datetime import datetime, timedelta, timezone
from agent.guardrails import GuardrailEngine
from agent.weather import WeatherReport


@pytest.fixture
def guardrails():
    return GuardrailEngine()


@pytest.fixture
def sunny_weather():
    return WeatherReport(
        temp_c=28.0,
        humidity_pct=45,
        description="Sunny / Clear",
        rain_expected_next_3h=False,
        rain_probability_pct=5,
        is_live_data=True,
    )


@pytest.fixture
def rainy_weather():
    return WeatherReport(
        temp_c=22.0,
        humidity_pct=85,
        description="Moderate Rain",
        rain_expected_next_3h=True,
        rain_probability_pct=80,
        is_live_data=True,
    )


def test_ai_skip_is_approved_directly(guardrails, sunny_weather):
    verdict = guardrails.evaluate(
        proposed_action="SKIP",
        proposed_duration_sec=0,
        current_moisture_pct=25.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is True
    assert verdict.final_action == "SKIP"
    assert verdict.final_duration_sec == 0


def test_drum_low_blocks_pump(guardrails, sunny_weather):
    """Safety Rule 1: Never run pump dry if drum level is LOW."""
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=20.0,  # Dry soil, AI wants to water
        drum_level="LOW",          # But drum is empty
        weather=sunny_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is False
    assert verdict.final_action == "SKIP"
    assert verdict.verdict_type == "BLOCKED"
    assert "Drum level is LOW" in verdict.reason


def test_soil_oversaturation_blocks_pump(guardrails, sunny_weather):
    """Safety Rule 2: Never water already wet soil (> 70%)."""
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=75.0,  # Already wet
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is False
    assert verdict.final_action == "SKIP"
    assert verdict.verdict_type == "BLOCKED"
    assert "above safe limit" in verdict.reason


def test_cooldown_blocks_rapid_watering(guardrails, sunny_weather):
    """Safety Rule 3: Must enforce minimum cooldown gap (2.0h) between waterings."""
    thirty_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=30)
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=28.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=thirty_minutes_ago,
        waterings_in_last_24h=1,
    )
    assert verdict.approved is False
    assert verdict.final_action == "SKIP"
    assert verdict.verdict_type == "BLOCKED"
    assert "Cooldown active" in verdict.reason


def test_cooldown_allows_watering_after_min_gap(guardrails, sunny_weather):
    """Safety Rule 3: Once 2.5 hours have elapsed, watering is allowed."""
    two_and_half_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2.5)
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=28.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=two_and_half_hours_ago,
        waterings_in_last_24h=1,
    )
    assert verdict.approved is True
    assert verdict.final_action == "WATER"


def test_daily_cap_blocks_excessive_watering(guardrails, sunny_weather):
    """Safety Rule 4: Hard cap of 4 waterings per 24 hours."""
    four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=4)
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=28.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=four_hours_ago,
        waterings_in_last_24h=4,  # Cap already reached
    )
    assert verdict.approved is False
    assert verdict.final_action == "SKIP"
    assert verdict.verdict_type == "BLOCKED"
    assert "Daily cap reached" in verdict.reason


def test_rain_forecast_conserves_water(guardrails, rainy_weather):
    """Safety Rule 5: If rain is expected in 3h and soil isn't critically dry, SKIP."""
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=32.0,  # Dry-ish, but not critical
        drum_level="OK",
        weather=rainy_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is False
    assert verdict.final_action == "SKIP"
    assert "Rain expected in next 3h" in verdict.reason


def test_duration_clamped_to_max(guardrails, sunny_weather):
    """Safety Rule 6: Excessive duration (e.g. 120s) must be clamped down to 45s."""
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=120,  # Excessive
        current_moisture_pct=28.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is True
    assert verdict.final_action == "WATER"
    assert verdict.final_duration_sec == 45  # Clamped to max_pump_seconds
    assert verdict.verdict_type == "MODIFIED"


def test_normal_dry_soil_watering_approved(guardrails, sunny_weather):
    """Baseline: Dry soil, drum OK, sunny weather, no prior runs -> Fully Approved."""
    verdict = guardrails.evaluate(
        proposed_action="WATER",
        proposed_duration_sec=30,
        current_moisture_pct=28.0,
        drum_level="OK",
        weather=sunny_weather,
        last_pump_time=None,
        waterings_in_last_24h=0,
    )
    assert verdict.approved is True
    assert verdict.final_action == "WATER"
    assert verdict.final_duration_sec == 30
    assert verdict.verdict_type == "APPROVED"
