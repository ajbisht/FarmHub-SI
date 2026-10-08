import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from agent.config import config

logger = logging.getLogger("Database")


class FarmDatabase:
    """SQLite storage for sensor readings, pump actuation history, and AI decisions.
    Includes automated 90-day retention cleanup.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates the database schema if tables do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. Soil and sensor readings
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    moisture_pct REAL NOT NULL,
                    raw_adc INTEGER,
                    drum_level TEXT NOT NULL,
                    battery_v REAL
                )
            """)

            # 2. Pump actuation events
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pump_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    duration_sec INTEGER NOT NULL,
                    reason TEXT,
                    trigger_source TEXT NOT NULL, -- 'AI_AGENT' or 'MANUAL_OVERRIDE'
                    status TEXT NOT NULL,         -- 'REQUESTED', 'ACKNOWLEDGED', 'VERIFIED', 'ANOMALY'
                    initial_moisture REAL,
                    verified_moisture REAL
                )
            """)

            # 3. AI decisions log (with full LLM reasoning)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    action TEXT NOT NULL,         -- 'WATER' or 'SKIP'
                    proposed_duration INTEGER,
                    approved_duration INTEGER,
                    reasoning TEXT NOT NULL,
                    guardrail_verdict TEXT NOT NULL, -- 'APPROVED', 'MODIFIED', 'BLOCKED'
                    weather_summary TEXT,
                    model_used TEXT
                )
            """)

            # Indexes for efficient queries
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_sensor_ts ON sensor_readings(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_pump_ts ON pump_events(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_ts ON ai_decisions(timestamp)")

            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    # --- Sensor Data Methods ---
    def record_reading(self, moisture_pct: float, raw_adc: Optional[int], drum_level: str, battery_v: Optional[float] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sensor_readings (moisture_pct, raw_adc, drum_level, battery_v)
                VALUES (?, ?, ?, ?)
            """, (moisture_pct, raw_adc, drum_level, battery_v))
            conn.commit()
            return cursor.lastrowid

    def get_latest_reading(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_recent_readings(self, hours: int = 24) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            since_time = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT * FROM sensor_readings WHERE timestamp >= ? ORDER BY timestamp ASC
            """, (since_time,))
            return [dict(row) for row in cursor.fetchall()]

    # --- Pump Events Methods ---
    def record_pump_event(self, duration_sec: int, reason: str, trigger_source: str, initial_moisture: float) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pump_events (duration_sec, reason, trigger_source, status, initial_moisture)
                VALUES (?, ?, ?, 'REQUESTED', ?)
            """, (duration_sec, reason, trigger_source, initial_moisture))
            conn.commit()
            return cursor.lastrowid

    def update_pump_status(self, event_id: int, status: str, verified_moisture: Optional[float] = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if verified_moisture is not None:
                cursor.execute("""
                    UPDATE pump_events SET status = ?, verified_moisture = ? WHERE id = ?
                """, (status, verified_moisture, event_id))
            else:
                cursor.execute("""
                    UPDATE pump_events SET status = ? WHERE id = ?
                """, (status, event_id))
            conn.commit()

    def get_last_pump_event(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM pump_events WHERE status IN ('REQUESTED', 'ACKNOWLEDGED', 'VERIFIED')
                ORDER BY timestamp DESC LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_waterings_in_last_24h(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            since_time = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                SELECT COUNT(*) as count FROM pump_events 
                WHERE timestamp >= ? AND status IN ('REQUESTED', 'ACKNOWLEDGED', 'VERIFIED')
            """, (since_time,))
            row = cursor.fetchone()
            return row["count"] if row else 0

    def get_consecutive_anomalies(self) -> int:
        """Returns the number of consecutive ANOMALY pump events since the last VERIFIED event."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status FROM pump_events 
                ORDER BY timestamp DESC LIMIT 5
            """)
            rows = cursor.fetchall()
            count = 0
            for r in rows:
                if r["status"] == "ANOMALY":
                    count += 1
                elif r["status"] == "VERIFIED":
                    break
            return count

    # --- AI Decisions Methods ---
    def record_decision(self, action: str, proposed_duration: int, approved_duration: int, reasoning: str, guardrail_verdict: str, weather_summary: str, model_used: str):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ai_decisions (action, proposed_duration, approved_duration, reasoning, guardrail_verdict, weather_summary, model_used)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (action, proposed_duration, approved_duration, reasoning, guardrail_verdict, weather_summary, model_used))
            conn.commit()

    def get_recent_decisions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM ai_decisions ORDER BY timestamp DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    # --- Retention Cleanup (90 days) ---
    def cleanup_old_records(self, days: int = 90) -> int:
        """Purges sensor logs older than 90 days to keep the Pi SD card lean."""
        cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff_date,))
            deleted = cursor.rowcount
            cursor.execute("DELETE FROM ai_decisions WHERE timestamp < ?", (cutoff_date,))
            conn.commit()
            if deleted > 0:
                logger.info(f"Purged {deleted} sensor readings older than {days} days.")
            return deleted
