import asyncio
import json
import logging
import os
import random
import sys
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Set, Dict, Any, Optional, List
from pydantic import BaseModel

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import paho.mqtt.client as mqtt
import httpx

# Add root directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import (
    config,
    TOPIC_SOIL_MOISTURE,
    TOPIC_DRUM_LEVEL,
    TOPIC_PUMP_COMMAND,
    TOPIC_PUMP_ACK,
    TOPIC_STATUS_HEARTBEAT,
    TOPIC_ALERT,
)
from agent.database import FarmDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DASHBOARD] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("DashboardServer")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class DashboardMQTTBridge:
    """Bridges MQTT field traffic to WebSocket connections in real time."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.db = FarmDatabase()
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.active_connections: Set[WebSocket] = set()

        # Initialize from database if records already exist
        latest_db = self.db.get_latest_reading()
        if latest_db:
            self.latest_state: Dict[str, Any] = {
                "moisture_pct": float(latest_db.get("moisture_pct", 0.0)),
                "raw_adc": latest_db.get("raw_adc", 0),
                "drum_level": latest_db.get("drum_level", "OK"),
                "battery_v": float(latest_db.get("battery_v", 12.2) or 12.2),
                "pump_state": "IDLE",
                "last_updated": latest_db.get("timestamp"),
                "automation_paused": False,
            }
        else:
            self.latest_state: Dict[str, Any] = {
                "moisture_pct": 0.0,
                "raw_adc": 0,
                "drum_level": "UNKNOWN",
                "battery_v": 12.0,
                "pump_state": "IDLE",
                "last_updated": None,
                "automation_paused": False,
            }

        client_id = f"dashboard_bridge_{random.randint(1000, 9999)}"
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except AttributeError:
            self.client = mqtt.Client(client_id=client_id)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        rc_code = rc.value if hasattr(rc, "value") else rc
        if rc_code == 0:
            logger.info(f"Dashboard MQTT Bridge connected to {self.host}:{self.port}")
            client.subscribe("farm/#", qos=1)
        else:
            logger.error(f"MQTT Bridge connection failed: {rc}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            # Ignore non-JSON or foreign payloads on public test broker
            return

        try:
            topic = msg.topic
            now_iso = datetime.now(timezone.utc).isoformat()

            if topic == TOPIC_SOIL_MOISTURE:
                moisture = float(payload.get("moisture_pct", 0.0))
                raw_adc = payload.get("raw", 0)
                self.latest_state["moisture_pct"] = moisture
                self.latest_state["raw_adc"] = raw_adc
                self.latest_state["last_updated"] = now_iso
                # Persist reading to database so 24-hour trend chart and history API populate
                self.db.record_reading(
                    moisture_pct=moisture,
                    raw_adc=raw_adc,
                    drum_level=self.latest_state.get("drum_level", "OK"),
                    battery_v=self.latest_state.get("battery_v", 12.0),
                )

            elif topic == TOPIC_DRUM_LEVEL:
                self.latest_state["drum_level"] = payload.get("level", "OK")
                self.latest_state["last_updated"] = now_iso

            elif topic == TOPIC_STATUS_HEARTBEAT:
                self.latest_state["battery_v"] = float(payload.get("battery_v", 12.0))
                self.latest_state["last_updated"] = now_iso

            elif topic == TOPIC_PUMP_COMMAND:
                action = payload.get("action", "")
                if action == "RUN":
                    self.latest_state["pump_state"] = "RUNNING"
                elif action == "STOP":
                    self.latest_state["pump_state"] = "IDLE"

            elif topic == TOPIC_PUMP_ACK:
                self.latest_state["pump_state"] = "IDLE"

            # Broadcast update to all connected WebSockets
            broadcast_msg = {
                "event": "FIELD_UPDATE",
                "topic": topic,
                "data": payload,
                "state": self.latest_state,
            }
            if self.loop and self.loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_json(broadcast_msg),
                    loop=self.loop,
                )

        except Exception as e:
            logger.error(f"Error handling MQTT message in Dashboard bridge: {e}")

    async def register(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        # Send initial snapshot immediately upon connection
        await websocket.send_json({
            "event": "INITIAL_SNAPSHOT",
            "state": self.latest_state,
        })
        logger.info(f"Client connected. Active clients: {len(self.active_connections)}")

    def unregister(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"Client disconnected. Active clients: {len(self.active_connections)}")

    async def broadcast_json(self, message: Dict[str, Any]):
        for ws in list(self.active_connections):
            try:
                await ws.send_json(message)
            except Exception:
                self.active_connections.discard(ws)

    def send_pump_command(self, action: str, duration_sec: int, reason: str):
        payload = {
            "action": action,
            "duration_sec": duration_sec,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.client.publish(TOPIC_PUMP_COMMAND, json.dumps(payload), qos=1, retain=True)
        logger.info(f"Manual command published to {TOPIC_PUMP_COMMAND}: {payload}")

    def start(self):
        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.warning(f"Could not connect to MQTT broker at {self.host}:{self.port}: {e}")
            if self.host == "localhost":
                logger.info("Falling back to public test broker (broker.hivemq.com:1883) for local development...")
                try:
                    self.host = "broker.hivemq.com"
                    self.client.connect(self.host, 1883, keepalive=60)
                    self.client.loop_start()
                except Exception as e2:
                    logger.error(f"Fallback MQTT connection failed: {e2}")

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()


bridge = DashboardMQTTBridge(host=config.mqtt_host, port=config.mqtt_port)
agent_service_instance = None
agent_worker_thread = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent_service_instance, agent_worker_thread
    # Startup: Capture the main event loop and start MQTT Bridge
    bridge.loop = asyncio.get_running_loop()
    bridge.start()

    # Boot the Autonomous Farm Agent Service in background thread
    run_agent = os.getenv("RUN_AGENT", "true").lower() in ("true", "1", "yes")
    if run_agent:
        logger.info("Booting FarmHub Autonomous AI Agent worker in FastAPI lifespan...")
        try:
            from agent.main import FarmAgentService
            agent_service_instance = FarmAgentService(host=bridge.host, port=bridge.port)
            agent_worker_thread = threading.Thread(
                target=agent_service_instance.run,
                name="FarmAgentWorkerThread",
                daemon=True,
            )
            agent_worker_thread.start()
            logger.info("FarmHub AI Agent worker successfully running.")
        except Exception as e:
            logger.error(f"Failed to start FarmAgentService in lifespan: {e}")

    yield

    # Shutdown: Stop Agent and MQTT Bridge
    if agent_service_instance:
        logger.info("Signaling background FarmHub Agent worker to shut down...")
        agent_service_instance.running = False
    bridge.stop()


app = FastAPI(title="FarmHub Irrigation Dashboard", lifespan=lifespan)

# Mount static directory for JS/CSS/manifest
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def get_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await bridge.register(websocket)
    try:
        while True:
            # Keep connection alive & handle incoming pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        bridge.unregister(websocket)
    except Exception:
        bridge.unregister(websocket)


@app.get("/api/status")
async def get_status():
    latest_db_reading = bridge.db.get_latest_reading()
    last_pump = bridge.db.get_last_pump_event()
    waterings_today = bridge.db.get_waterings_in_last_24h()

    return {
        "live": bridge.latest_state,
        "database_latest": latest_db_reading,
        "last_pump": last_pump,
        "waterings_24h": waterings_today,
        "dry_run": config.dry_run,
        "location": config.location_name,
    }


@app.get("/api/history")
async def get_history(hours: int = 24):
    readings = bridge.db.get_recent_readings(hours=hours)
    return {"readings": readings}


@app.get("/api/decisions")
async def get_decisions(limit: int = 15):
    decisions = bridge.db.get_recent_decisions(limit=limit)
    return {"decisions": decisions}


@app.post("/api/override/water")
async def override_water(duration_sec: int = 30):
    if bridge.latest_state["drum_level"] == "LOW":
        raise HTTPException(
            status_code=400,
            detail="Cannot water: Drum water level is LOW. Refill reservoir first.",
        )

    # Record manual pump event in database
    current_moisture = bridge.latest_state["moisture_pct"]
    bridge.db.record_pump_event(
        duration_sec=duration_sec,
        reason="Manual Water Now triggered from Dashboard UI",
        trigger_source="MANUAL_OVERRIDE",
        initial_moisture=current_moisture,
    )

    bridge.send_pump_command("RUN", duration_sec, "Manual Override from Dashboard")
    return {"status": "SUCCESS", "message": f"Watering initiated for {duration_sec}s."}


@app.post("/api/override/stop")
async def override_stop():
    bridge.send_pump_command("STOP", 0, "Emergency Stop from Dashboard")
    bridge.latest_state["pump_state"] = "IDLE"
    return {"status": "SUCCESS", "message": "Emergency STOP command transmitted."}


@app.post("/api/override/toggle-pause")
async def toggle_pause():
    bridge.latest_state["automation_paused"] = not bridge.latest_state["automation_paused"]
    state_str = "PAUSED" if bridge.latest_state["automation_paused"] else "ACTIVE"
    return {"status": "SUCCESS", "automation_paused": bridge.latest_state["automation_paused"], "message": f"Automation is now {state_str}."}


@app.get("/api/groq-models")
async def get_groq_models():
    """Diagnostic endpoint to inspect active models enabled on Groq."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {config.groq_api_key}"},
            )
            data = r.json()
            model_ids = [m["id"] for m in data.get("data", [])]
            return {"status": r.status_code, "models": model_ids}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/evaluate-now")
async def trigger_evaluate_now():
    """Forces an immediate AI evaluation cycle with LLM + weather + guardrails."""
    from agent.weather import WeatherClient
    from agent.llm_client import LLMClient
    from agent.guardrails import GuardrailEngine

    weather = WeatherClient().get_forecast()
    llm = LLMClient()
    guardrails = GuardrailEngine()

    moisture = float(bridge.latest_state.get("moisture_pct", 30.0))
    drum = str(bridge.latest_state.get("drum_level", "OK"))
    history = bridge.db.get_recent_readings(hours=12)

    last_pump_event = bridge.db.get_last_pump_event()
    last_pump_time = None
    if last_pump_event:
        try:
            last_pump_time = datetime.strptime(last_pump_event["timestamp"], "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    waterings_24h = bridge.db.get_waterings_in_last_24h()

    decision = llm.decide(
        current_moisture_pct=moisture,
        drum_level=drum,
        weather=weather,
        recent_history=history,
    )

    battery = float(bridge.latest_state.get("battery_v", 12.0) or 12.0)
    raw_adc = int(bridge.latest_state.get("raw_adc", 2000) or 2000)
    consecutive_failures = bridge.db.get_consecutive_anomalies()

    verdict = guardrails.evaluate(
        proposed_action=decision.action,
        proposed_duration_sec=decision.duration_sec,
        current_moisture_pct=moisture,
        drum_level=drum,
        weather=weather,
        last_pump_time=last_pump_time,
        waterings_in_last_24h=waterings_24h,
        battery_v=battery,
        raw_adc=raw_adc,
        consecutive_verification_failures=consecutive_failures,
    )

    bridge.db.record_decision(
        action=verdict.final_action,
        proposed_duration=decision.duration_sec,
        approved_duration=verdict.final_duration_sec,
        reasoning=f"AI: {decision.reasoning} | Policy: {verdict.reason}",
        guardrail_verdict=verdict.verdict_type,
        weather_summary=f"{weather.description}, {weather.temp_c}C",
        model_used=decision.model_name,
    )

    if verdict.final_action == "WATER" and verdict.approved:
        bridge.send_pump_command("RUN", verdict.final_duration_sec, verdict.reason)

    return {
        "status": "SUCCESS",
        "action": verdict.final_action,
        "duration_sec": verdict.final_duration_sec,
        "engine": decision.model_name,
        "reasoning": decision.reasoning,
        "guardrail_verdict": verdict.verdict_type,
    }


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None


@app.post("/api/chat")
async def chat_with_farmhub(request: ChatRequest):
    """Conversational endpoint for the dashboard AI chatbot."""
    from agent.chat_client import FarmChatAgent
    from agent.weather import WeatherClient

    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    chat_agent = FarmChatAgent()
    try:
        weather = WeatherClient().get_forecast()
    except Exception:
        weather = None

    decisions = bridge.db.get_recent_decisions(limit=5)
    waterings_24h = bridge.db.get_waterings_in_last_24h()

    # Prefer live telemetry from bridge, fallback to db latest if available
    telemetry = dict(bridge.latest_state)
    if telemetry.get("moisture_pct", 0) == 0:
        latest_db = bridge.db.get_latest_reading()
        if latest_db:
            telemetry["moisture_pct"] = float(latest_db.get("moisture_pct", 0.0))
            telemetry["raw_adc"] = latest_db.get("raw_adc", telemetry.get("raw_adc", 0))
            telemetry["drum_level"] = latest_db.get("drum_level", telemetry.get("drum_level", "OK"))
            telemetry["battery_v"] = float(latest_db.get("battery_v", 12.2) or 12.2)

    reply = chat_agent.chat(
        user_message=request.message.strip(),
        conversation_history=request.history or [],
        telemetry=telemetry,
        weather=weather,
        decisions=decisions,
        waterings_24h=waterings_24h,
    )

    return {
        "reply": reply,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "location": config.location_name,
    }


if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0", help="Binding host")
    parser.add_argument("--port", type=int, default=8000, help="Binding port")
    parser.add_argument("--mqtt-host", default=config.mqtt_host, help="MQTT host")
    args = parser.parse_args()

    bridge.host = args.mqtt_host
    uvicorn.run("dashboard.server:app", host=args.host, port=args.port, reload=False)
