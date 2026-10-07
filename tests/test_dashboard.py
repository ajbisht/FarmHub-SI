import pytest
from fastapi.testclient import TestClient
from dashboard.server import app, bridge


@pytest.fixture
def client():
    # Use TestClient with app
    with TestClient(app) as test_client:
        yield test_client


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "FarmHub" in response.text
    assert "Soil Moisture" in response.text


def test_api_status_endpoint(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "live" in data
    assert "waterings_24h" in data
    assert "location" in data


def test_api_history_endpoint(client):
    response = client.get("/api/history?hours=24")
    assert response.status_code == 200
    data = response.json()
    assert "readings" in data


def test_api_decisions_endpoint(client):
    response = client.get("/api/decisions?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "decisions" in data


def test_override_water_blocked_on_drum_low(client):
    # Simulate drum level LOW in bridge state
    original_level = bridge.latest_state["drum_level"]
    bridge.latest_state["drum_level"] = "LOW"
    try:
        response = client.post("/api/override/water?duration_sec=30")
        assert response.status_code == 400
        assert "Drum water level is LOW" in response.json()["detail"]
    finally:
        bridge.latest_state["drum_level"] = original_level


def test_override_water_allowed_on_drum_ok(client):
    original_level = bridge.latest_state["drum_level"]
    bridge.latest_state["drum_level"] = "OK"
    try:
        response = client.post("/api/override/water?duration_sec=30")
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"
    finally:
        bridge.latest_state["drum_level"] = original_level
