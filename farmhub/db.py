"""FarmHub Clean Database Layer (SQLite).

Provides persistent storage for time-series telemetry, agentic AI decisions,
and closed-loop water delivery verification audits.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "farmhub_poc.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db(reset: bool = False):
    """Initialize or completely reset the database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    if reset:
        cursor.execute("DROP TABLE IF EXISTS telemetry_logs")
        cursor.execute("DROP TABLE IF EXISTS agent_decisions")
        cursor.execute("DROP TABLE IF EXISTS water_delivery_events")
        cursor.execute("DROP TABLE IF EXISTS system_alerts")

    # 1. Telemetry Readings Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_epoch INTEGER,
            iso_time TEXT,
            soil_moisture_vwc_pct REAL,
            soil_raw_adc INTEGER,
            drum_liters REAL,
            drum_pct REAL,
            reservoir_level_ok INTEGER,
            pump_running INTEGER,
            battery_v REAL,
            rssi_dbm INTEGER
        )
    """)

    # 2. Agentic Decisions & Tool Traces Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_epoch INTEGER,
            iso_time TEXT,
            intent TEXT,
            proposed_action TEXT,
            authorized INTEGER,
            authorized_duration_sec INTEGER,
            safety_reason TEXT,
            rule_triggered TEXT,
            field_message TEXT,
            tools_called TEXT
        )
    """)

    # 3. Closed-Loop Water Delivery Audits Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS water_delivery_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp_epoch INTEGER,
            iso_time TEXT,
            duration_sec INTEGER,
            liters_delivered REAL,
            pre_moisture REAL,
            post_moisture REAL,
            delta_pct REAL,
            verified INTEGER,
            delivery_fault INTEGER
        )
    """)

    conn.commit()
    conn.close()

def log_telemetry(payload: Dict[str, Any]):
    """Insert a raw telemetry reading."""
    conn = get_connection()
    cursor = conn.cursor()
    now_epoch = payload.get("timestamp", int(time.time()))
    iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_epoch))

    drum = payload.get("drum_level", {})
    liters = drum.get("liters", 160.0) if isinstance(drum, dict) else 160.0
    pct = drum.get("pct", 80.0) if isinstance(drum, dict) else 80.0

    cursor.execute("""
        INSERT INTO telemetry_logs (
            timestamp_epoch, iso_time, soil_moisture_vwc_pct, soil_raw_adc,
            drum_liters, drum_pct, reservoir_level_ok, pump_running, battery_v, rssi_dbm
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_epoch, iso_time,
        payload.get("soil_moisture_vwc_pct", payload.get("moisture_pct", 38.0)),
        payload.get("soil_raw_adc", payload.get("raw_adc", 2100)),
        liters, pct,
        1 if payload.get("reservoir_level_ok", True) else 0,
        1 if payload.get("pump_running", False) else 0,
        payload.get("battery_v", 12.35),
        payload.get("rssi_dbm", -55)
    ))
    conn.commit()
    conn.close()

def log_agent_decision(decision: Dict[str, Any]):
    """Insert an agentic decision and tool execution trace."""
    conn = get_connection()
    cursor = conn.cursor()
    now_epoch = int(time.time())
    iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_epoch))

    verdict = decision.get("agent_verdict", {})
    cursor.execute("""
        INSERT INTO agent_decisions (
            timestamp_epoch, iso_time, intent, proposed_action,
            authorized, authorized_duration_sec, safety_reason,
            rule_triggered, field_message, tools_called
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_epoch, iso_time,
        decision.get("intent", "EVALUATE"),
        verdict.get("proposed_action", "MONITOR"),
        1 if verdict.get("authorized", False) else 0,
        verdict.get("authorized_duration_sec", 0),
        verdict.get("safety_reason", ""),
        verdict.get("rule_triggered", ""),
        decision.get("field_message", ""),
        json.dumps([t.get("tool") for t in decision.get("tool_calls_trace", [])])
    ))
    conn.commit()
    conn.close()

def log_delivery_event(event: Dict[str, Any]):
    """Log an irrigation pulse and its soil moisture response verification."""
    conn = get_connection()
    cursor = conn.cursor()
    now_epoch = int(time.time())
    iso_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_epoch))

    cursor.execute("""
        INSERT INTO water_delivery_events (
            timestamp_epoch, iso_time, duration_sec, liters_delivered,
            pre_moisture, post_moisture, delta_pct, verified, delivery_fault
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        now_epoch, iso_time,
        event.get("duration_sec", 25),
        event.get("liters_delivered", 3.0),
        event.get("pre_moisture", 20.0),
        event.get("post_moisture", 36.0),
        event.get("delta_pct", 16.0),
        1 if event.get("verified", True) else 0,
        1 if event.get("delivery_fault", False) else 0
    ))
    conn.commit()
    conn.close()

def get_recent_history(limit: int = 30) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT iso_time, soil_moisture_vwc_pct, soil_raw_adc, drum_liters
        FROM telemetry_logs
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "timestamp": row["iso_time"],
            "moisture_pct": row["soil_moisture_vwc_pct"],
            "raw_adc": row["soil_raw_adc"],
            "drum_liters": row["drum_liters"]
        }
        for row in reversed(rows)
    ]

def get_recent_decisions(limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT iso_time, proposed_action, authorized, field_message, safety_reason, tools_called
        FROM agent_decisions
        ORDER BY id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "timestamp": row["iso_time"],
            "action": row["proposed_action"],
            "authorized": bool(row["authorized"]),
            "reasoning": row["field_message"],
            "safety_reason": row["safety_reason"],
            "tools": json.loads(row["tools_called"] or "[]")
        }
        for row in rows
    ]
