import pytest
from fastapi.testclient import TestClient
from dashboard.server import app, bridge
from agent.chat_client import FarmChatAgent


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_chat_endpoint_empty_message_rejected(client):
    response = client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 400
    assert "Message cannot be empty" in response.json()["detail"]


def test_chat_endpoint_valid_query(client):
    response = client.post(
        "/api/chat",
        json={
            "message": "How are the tomato plants doing?",
            "history": []
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert len(data["reply"]) > 10
    assert "timestamp" in data
    assert "location" in data


def test_farm_chat_agent_fallback_telemetry():
    agent = FarmChatAgent()
    telemetry = {
        "moisture_pct": 32.5,
        "drum_level": "OK",
        "battery_v": 12.1,
        "pump_state": "IDLE"
    }
    response = agent._local_fallback(
        query="How are the plants?",
        telemetry=telemetry,
        weather=None,
        decisions=[]
    )
    assert "32.5%" in response
    assert "12.1V" in response
    assert "Plant Health" in response


def test_farm_chat_agent_fallback_weather():
    agent = FarmChatAgent()
    response = agent._local_fallback(
        query="What is the weather like?",
        telemetry={"moisture_pct": 50.0},
        weather=None,
        decisions=[]
    )
    assert "Local Weather" in response
