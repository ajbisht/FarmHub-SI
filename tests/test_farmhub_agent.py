"""Unit Tests for FarmHub ReAct Agent and Deterministic Safety Gatekeeper."""

import pytest
from farmhub.safety import DeterministicSafetyGuardrail, SafetyVerdict
from farmhub.agent import FarmHubAgent
from farmhub.weather import WeatherService

class MockWeatherService(WeatherService):
    def __init__(self, rain_prob: int = 10):
        super().__init__()
        self.rain_prob = rain_prob

    def fetch_forecast(self):
        return {
            "temperature_c": 22.5,
            "humidity_pct": 55,
            "weather_code": 0,
            "rain_probability_pct": self.rain_prob,
            "rain_expected_soon": self.rain_prob >= 60,
            "status": "MOCK"
        }

@pytest.fixture
def mock_crop_config():
    return {
        "title": "Terrace Bed: 5 Tomato Plants",
        "target_min": 30.0,
        "target_max": 55.0,
        "watering_duration_sec": 25,
        "cooldown_hours": 2.0
    }

def test_safety_blocks_empty_reservoir(mock_crop_config):
    guardrail = DeterministicSafetyGuardrail()
    telemetry = {
        "soil_moisture_vwc_pct": 18.0,
        "reservoir_level_ok": False,
        "cooldown_remaining_sec": 0,
        "delivery_fault": False
    }
    verdict = guardrail.evaluate("WATER", 25, telemetry, mock_crop_config)
    assert not verdict.allowed
    assert verdict.rule_triggered == "RESERVOIR_EMPTY_CUTOFF"
    assert "reservoir is empty" in verdict.reason.lower()

def test_safety_blocks_active_cooldown(mock_crop_config):
    guardrail = DeterministicSafetyGuardrail()
    telemetry = {
        "soil_moisture_vwc_pct": 18.0,
        "reservoir_level_ok": True,
        "cooldown_remaining_sec": 3600, # 1 hour left
        "delivery_fault": False
    }
    verdict = guardrail.evaluate("WATER", 25, telemetry, mock_crop_config)
    assert not verdict.allowed
    assert verdict.rule_triggered == "COOLDOWN_ACTIVE"
    assert "cooldown active" in verdict.reason.lower()

def test_safety_blocks_delivery_fault(mock_crop_config):
    guardrail = DeterministicSafetyGuardrail()
    telemetry = {
        "soil_moisture_vwc_pct": 18.0,
        "reservoir_level_ok": True,
        "cooldown_remaining_sec": 0,
        "delivery_fault": True
    }
    verdict = guardrail.evaluate("WATER", 25, telemetry, mock_crop_config)
    assert not verdict.allowed
    assert verdict.rule_triggered == "DELIVERY_FAULT"
    assert "did not raise soil moisture" in verdict.reason.lower()

def test_safety_clamps_duration_to_30s(mock_crop_config):
    guardrail = DeterministicSafetyGuardrail(max_duration_sec=30)
    telemetry = {
        "soil_moisture_vwc_pct": 20.0,
        "reservoir_level_ok": True,
        "cooldown_remaining_sec": 0,
        "delivery_fault": False
    }
    verdict = guardrail.evaluate("WATER", 60, telemetry, mock_crop_config) # Request 60s
    assert verdict.allowed
    assert verdict.clamped_duration_sec == 30 # Clamped to 30s

def test_agent_rain_conservation(mock_crop_config):
    weather = MockWeatherService(rain_prob=85)
    agent = FarmHubAgent(weather_service=weather)
    telemetry = {
        "soil_moisture_vwc_pct": 22.0, # Dry, but rain is coming
        "reservoir_level_ok": True,
        "cooldown_remaining_sec": 0,
        "delivery_fault": False
    }
    result = agent.run_agentic_cycle(telemetry, mock_crop_config)
    assert result["agent_verdict"]["proposed_action"] == "WAIT"
    assert "rain" in result["field_message"].lower()

def test_agent_watering_approval_and_field_tone(mock_crop_config):
    weather = MockWeatherService(rain_prob=10) # Clear skies
    agent = FarmHubAgent(weather_service=weather)
    telemetry = {
        "soil_moisture_vwc_pct": 20.0, # Thirsty
        "reservoir_level_ok": True,
        "cooldown_remaining_sec": 0,
        "delivery_fault": False
    }
    result = agent.run_agentic_cycle(telemetry, mock_crop_config)
    assert result["agent_verdict"]["proposed_action"] == "WATER"
    assert result["agent_verdict"]["authorized"] is True
    # Phrasing must be concise (<12 words)
    words = result["field_message"].split()
    assert len(words) <= 12
