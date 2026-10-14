"""FarmHub AI Mission Control & Telemetry Server (FastAPI).

Serves the modern Command Deck dashboard, manages live WebSocket connections,
ingests ESP32 edge telemetry, and executes the ReAct Agentic decision cycle.
"""

import os
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from farmhub.agent import FarmHubAgent
from farmhub.weather import WeatherService
from farmhub import db

# Initialize clean database tables
db.init_db(reset=False)

app = FastAPI(title="FarmHub AI Mission Control", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Server State ---
agent = FarmHubAgent()
connected_websockets: List[WebSocket] = []

STATIC_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "static"
if not STATIC_DIR.exists():
    STATIC_DIR = Path(__file__).resolve().parent.parent / "farmhub-dashboard" / "static"
CROPS_CONFIG_PATH = STATIC_DIR / "crops_config.json"

# In-Memory Telemetry State
current_telemetry: Dict[str, Any] = {
    "device_id": "farmhub-node-01",
    "timestamp": int(time.time()),
    "soil_moisture_vwc_pct": 34.2,
    "soil_raw_adc": 2180,
    "reservoir_level_ok": True,
    "pump_running": False,
    "cooldown_remaining_sec": 0,
    "total_cycles_today": 1,
    "delivery_verified": True,
    "delivery_fault": False,
    "drum_level": {
        "liters": 180.0,
        "pct": 90.0,
        "float_switch_ok": True
    },
    "drum_liters": 180.0,
    "drum_pct": 90.0,
    "battery_v": 12.35,
    "rssi_dbm": -56,
    "active_crop": "tomatoes",
    "automation_paused": False
}

latest_agent_decision: Dict[str, Any] = {
    "action": "MONITOR",
    "reasoning": "Soil is healthy and moist at 34%. Plants are happy.",
    "model": "Field Agronomist ReAct Engine",
    "timestamp": "Just now",
    "authorized": True
}

decision_history: List[Dict[str, Any]] = []
telemetry_history: List[Dict[str, Any]] = []

def get_crop_config(preset_key: str = "tomatoes") -> Dict[str, Any]:
    if CROPS_CONFIG_PATH.exists():
        try:
            with open(CROPS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("presets", {}).get(preset_key, {})
        except Exception:
            pass
    # Fallback Tomato preset
    return {
        "title": "Terrace Bed: 5 Tomato Plants",
        "target_min": 25.0,
        "target_max": 55.0,
        "watering_duration_sec": 25,
        "cooldown_hours": 2.0
    }

# --- WebSocket Hub ---
async def broadcast_ws(event_type: str, state_data: Dict[str, Any]):
    dead_sockets = []
    payload = json.dumps({"event": event_type, "state": state_data})
    for ws in connected_websockets:
        try:
            await ws.send_text(payload)
        except Exception:
            dead_sockets.append(ws)
    for ws in dead_sockets:
        if ws in connected_websockets:
            connected_websockets.remove(ws)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_websockets.append(websocket)
    # Send initial snapshot
    await websocket.send_text(json.dumps({
        "event": "INITIAL_SNAPSHOT",
        "state": {
            **current_telemetry,
            "agent_message": latest_agent_decision["reasoning"],
            "agent_action": latest_agent_decision["action"]
        }
    }))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in connected_websockets:
            connected_websockets.remove(websocket)

# --- API Endpoints ---
@app.post("/api/telemetry")
async def ingest_telemetry(payload: Dict[str, Any]):
    """Ingest live telemetry from ESP32 Edge Node 1."""
    global current_telemetry
    current_telemetry.update(payload)
    current_telemetry["timestamp"] = int(time.time())

    # Ensure drum fields are synced
    if "drum_level" in payload and isinstance(payload["drum_level"], dict):
        current_telemetry["drum_liters"] = payload["drum_level"].get("liters", current_telemetry.get("drum_liters", 180.0))
        current_telemetry["drum_pct"] = payload["drum_level"].get("pct", current_telemetry.get("drum_pct", 90.0))
        if "float_switch_ok" in payload["drum_level"]:
            current_telemetry["reservoir_level_ok"] = payload["drum_level"]["float_switch_ok"]
    elif "drum_liters" in payload:
        liters = payload["drum_liters"]
        pct = payload.get("drum_pct", (liters / 200.0) * 100)
        current_telemetry["drum_level"] = {
            "liters": liters,
            "pct": pct,
            "float_switch_ok": current_telemetry.get("reservoir_level_ok", True)
        }

    # Record time-series history for Chart.js
    telemetry_history.append({
        "time": time.strftime("%H:%M"),
        "moisture": current_telemetry.get("soil_moisture_vwc_pct", 0),
        "adc": current_telemetry.get("soil_raw_adc", 0)
    })
    if len(telemetry_history) > 100:
        telemetry_history.pop(0)

    # Persist to SQLite Database
    try:
        db.log_telemetry(current_telemetry)
    except Exception as e:
        print(f"[DB Error] log_telemetry: {e}")

    # Broadcast update to connected dashboards with both field names
    broadcast_payload = {
        **current_telemetry,
        "moisture_pct": current_telemetry.get("soil_moisture_vwc_pct", 38.0),
        "raw_adc": current_telemetry.get("soil_raw_adc", 2100),
        "battery_v": current_telemetry.get("battery_v", 12.35),
        "drum_level": current_telemetry.get("drum_level", {
            "liters": current_telemetry.get("drum_liters", 180.0),
            "pct": current_telemetry.get("drum_pct", 90.0),
            "float_switch_ok": current_telemetry.get("reservoir_level_ok", True)
        }),
        "drum_liters": current_telemetry.get("drum_liters", 180.0),
        "drum_pct": current_telemetry.get("drum_pct", 90.0),
        "reservoir_level_ok": current_telemetry.get("reservoir_level_ok", True),
        "agent_message": latest_agent_decision.get("reasoning", ""),
        "agent_action": latest_agent_decision.get("action", "MONITOR")
    }
    await broadcast_ws("FIELD_UPDATE", broadcast_payload)

    # Return status and any pending actuation command
    if current_telemetry.get("pending_command"):
        cmd = current_telemetry.pop("pending_command")
        return {"status": "SUCCESS", "command": cmd}
    return {"status": "SUCCESS"}

@app.get("/api/status")
async def get_status():
    live_state = {
        **current_telemetry,
        "moisture_pct": current_telemetry.get("soil_moisture_vwc_pct", 38.0),
        "raw_adc": current_telemetry.get("soil_raw_adc", 2100),
        "battery_v": current_telemetry.get("battery_v", 12.35),
        "drum_level": current_telemetry.get("drum_level", {
            "liters": current_telemetry.get("drum_liters", 180.0),
            "pct": current_telemetry.get("drum_pct", 90.0),
            "float_switch_ok": current_telemetry.get("reservoir_level_ok", True)
        }),
        "drum_liters": current_telemetry.get("drum_liters", 180.0),
        "drum_pct": current_telemetry.get("drum_pct", 90.0),
        "reservoir_level_ok": current_telemetry.get("reservoir_level_ok", True)
    }
    return {
        "telemetry": current_telemetry,
        "live": live_state,
        "decision": latest_agent_decision,
        "waterings_24h": current_telemetry.get("total_cycles_today", 1)
    }

@app.post("/api/evaluate-now")
async def evaluate_now():
    """Trigger the ReAct Agentic cycle immediately."""
    global latest_agent_decision
    crop_conf = get_crop_config(current_telemetry.get("active_crop", "tomatoes"))
    result = agent.run_agentic_cycle(current_telemetry, crop_conf)

    latest_agent_decision = {
        "action": result["agent_verdict"]["proposed_action"],
        "reasoning": result["field_message"],
        "model": "Field Agronomist ReAct Engine",
        "timestamp": time.strftime("%H:%M:%S"),
        "authorized": result["agent_verdict"]["authorized"],
        "safety_reason": result["agent_verdict"]["safety_reason"],
        "tool_trace": result["tool_calls_trace"]
    }
    decision_history.insert(0, latest_agent_decision)
    if len(decision_history) > 20:
        decision_history.pop()

    # Persist decision to SQLite Database
    try:
        db.log_agent_decision(result)
    except Exception as e:
        print(f"[DB Error] log_agent_decision: {e}")

    # If action is authorized watering, queue command for ESP32
    if result["agent_verdict"]["authorized"] and result["agent_verdict"]["proposed_action"] == "WATER":
        dur = result["agent_verdict"]["authorized_duration_sec"]
        current_telemetry["pending_command"] = f"IRRIGATE_CYCLE_{dur}"
        current_telemetry["pump_running"] = True

    await broadcast_ws("FIELD_UPDATE", {
        **current_telemetry,
        "agent_message": latest_agent_decision["reasoning"],
        "agent_action": latest_agent_decision["action"]
    })
    return result

@app.post("/api/override/water")
async def override_water(duration_sec: int = Query(20, ge=5, le=30)):
    """Manual watering pulse gated by hardware safety."""
    if not current_telemetry.get("reservoir_level_ok", True):
        raise HTTPException(status_code=400, detail="Cannot water: Water reservoir is empty!")

    dur = min(duration_sec, 30)
    current_telemetry["pending_command"] = f"IRRIGATE_CYCLE_{dur}"
    current_telemetry["pump_running"] = True
    await broadcast_ws("FIELD_UPDATE", current_telemetry)
    return {"status": "SUCCESS", "command": f"IRRIGATE_CYCLE_{dur}"}

@app.post("/api/override/stop")
async def override_stop():
    current_telemetry["pending_command"] = "STOP"
    current_telemetry["pump_running"] = False
    await broadcast_ws("FIELD_UPDATE", current_telemetry)
    return {"status": "SUCCESS"}

@app.post("/api/override/toggle-pause")
async def toggle_pause():
    current_telemetry["automation_paused"] = not current_telemetry.get("automation_paused", False)
    await broadcast_ws("FIELD_UPDATE", current_telemetry)
    return {"status": "SUCCESS", "automation_paused": current_telemetry["automation_paused"]}

@app.post("/api/db/reset")
async def reset_db_endpoint():
    """Completely wipe and re-initialize the FarmHub POC database."""
    global current_telemetry, latest_agent_decision, decision_history, telemetry_history
    db.init_db(reset=True)
    telemetry_history.clear()
    decision_history.clear()
    current_telemetry = {
        "device_id": "farmhub-node-01",
        "timestamp": int(time.time()),
        "soil_moisture_vwc_pct": 38.0,
        "soil_raw_adc": 2150,
        "reservoir_level_ok": True,
        "pump_running": False,
        "cooldown_remaining_sec": 0,
        "total_cycles_today": 0,
        "delivery_verified": True,
        "delivery_fault": False,
        "battery_v": 12.4,
        "drum_level": {
            "liters": 180.0,
            "pct": 90.0,
            "float_switch_ok": True
        },
        "pump_state": "IDLE",
        "rssi_dbm": -55,
        "active_crop": "tomatoes",
        "automation_paused": False
    }
    latest_agent_decision = {
        "action": "MONITOR",
        "reasoning": "Database reset. Soil is healthy at 38%.",
        "model": "Field Agronomist ReAct Engine",
        "timestamp": "Just now",
        "authorized": True
    }
    broadcast_payload = {
        **current_telemetry,
        "moisture_pct": current_telemetry.get("soil_moisture_vwc_pct", 38.0),
        "raw_adc": current_telemetry.get("soil_raw_adc", 2150),
        "drum_liters": current_telemetry.get("drum_level", {}).get("liters", 180.0),
        "drum_pct": current_telemetry.get("drum_level", {}).get("pct", 90.0),
        "agent_message": latest_agent_decision.get("reasoning", ""),
        "agent_action": latest_agent_decision.get("action", "MONITOR")
    }
    await broadcast_ws("FIELD_UPDATE", broadcast_payload)
    return {"status": "SUCCESS", "message": "Database wiped clean and telemetry reset to pristine baseline."}

@app.get("/api/history")
async def get_history():
    rows = db.get_recent_history(30)
    if rows:
        return {"readings": rows}
    return {"readings": telemetry_history[-30:]}

@app.get("/api/decisions")
async def get_decisions():
    rows = db.get_recent_decisions(10)
    if rows:
        return {"decisions": rows}
    return {"decisions": decision_history[:10]}

# --- Static File Serving ---
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")
