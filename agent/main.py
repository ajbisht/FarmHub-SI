import argparse
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure project root is in path
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
from agent.weather import WeatherClient
from agent.llm_client import LLMClient
from agent.guardrails import GuardrailEngine
import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FARM-AGENT] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("FarmAgent")


class FarmAgentService:
    """The Autonomous AI Agent Service running on the Raspberry Pi.
    Coordinates MQTT messaging, sensor telemetry, weather forecasts,
    LLM decision-making, code guardrails, and verification scheduling.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None):
        self.host = host or config.mqtt_host
        self.port = port or config.mqtt_port
        self.db = FarmDatabase()
        self.weather_client = WeatherClient()
        self.llm_client = LLMClient()
        self.guardrails = GuardrailEngine()

        self.running = True
        self.latest_moisture: Optional[float] = None
        self.latest_drum_level: str = "OK"
        self.latest_battery_v: Optional[float] = None
        self.last_decision_time: Optional[datetime] = None

        # Verification scheduler state
        self.pending_verification_event_id: Optional[int] = None
        self.pending_verification_time: Optional[datetime] = None
        self.initial_verification_moisture: Optional[float] = None

        import random
        client_id = f"farmhub_ai_agent_{random.randint(1000, 9999)}"
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
        except AttributeError:
            self.client = mqtt.Client(client_id=client_id)

        self._setup_mqtt()

    def _setup_mqtt(self):
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        rc_code = rc.value if hasattr(rc, "value") else rc
        if rc_code == 0:
            logger.info(f"Connected to MQTT Broker at {self.host}:{self.port}")
            # Subscribe to all sensor & field topics
            client.subscribe(TOPIC_SOIL_MOISTURE, qos=1)
            client.subscribe(TOPIC_DRUM_LEVEL, qos=1)
            client.subscribe(TOPIC_PUMP_ACK, qos=1)
            client.subscribe(TOPIC_STATUS_HEARTBEAT, qos=1)
            logger.info("Subscribed to field telemetry topics.")
        else:
            logger.error(f"MQTT connection failed with code: {rc}")

    def _on_disconnect(self, client, userdata, *args):
        logger.warning(f"Disconnected from MQTT broker.")

    def _on_message(self, client, userdata, msg):
        """Processes incoming telemetric packets from the ESP32 field node."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic

            if topic == TOPIC_SOIL_MOISTURE:
                moisture = float(payload.get("moisture_pct", 0.0))
                raw_adc = payload.get("raw")
                self.latest_moisture = moisture
                self.db.record_reading(
                    moisture_pct=moisture,
                    raw_adc=raw_adc,
                    drum_level=self.latest_drum_level,
                    battery_v=self.latest_battery_v,
                )
                logger.info(f"Soil Reading Received: {moisture:.1f}% (ADC: {raw_adc})")

                # Check if we have a pending verification
                self._check_pending_verification(moisture)

                # Trigger autonomous evaluation
                self._evaluate_irrigation_cycle()

            elif topic == TOPIC_DRUM_LEVEL:
                level = payload.get("level", "OK")
                self.latest_drum_level = level
                if level == "LOW":
                    logger.warning("ALERT: Drum water level is LOW! Alerting dashboard.")
                    self.publish_alert("LOW_DRUM", "Drum reservoir water is LOW. Refill required.")

            elif topic == TOPIC_PUMP_ACK:
                logger.info(f"ESP32 confirmed pump actuation: {payload}")
                last_event = self.db.get_last_pump_event()
                if last_event and last_event["status"] == "REQUESTED":
                    self.db.update_pump_status(last_event["id"], "ACKNOWLEDGED")

            elif topic == TOPIC_STATUS_HEARTBEAT:
                self.latest_battery_v = float(payload.get("battery_v", 12.0))
                rssi = payload.get("rssi", -60)
                logger.debug(f"ESP32 Heartbeat: Battery={self.latest_battery_v}V, RSSI={rssi}dBm")

        except Exception as e:
            logger.error(f"Error handling MQTT message on {msg.topic}: {e}")

    def _evaluate_irrigation_cycle(self):
        """Evaluates whether to water based on moisture, history, weather, and AI guardrails."""
        if self.latest_moisture is None:
            return

        # Throttle evaluation cycle: run every SENSE_INTERVAL_MIN (or immediately if first time)
        now = datetime.now(timezone.utc)
        if self.last_decision_time:
            elapsed_min = (now - self.last_decision_time).total_seconds() / 60.0
            if elapsed_min < config.sense_interval_min:
                return

        self.last_decision_time = now
        logger.info("=== STARTING AUTONOMOUS IRRIGATION EVALUATION CYCLE ===")

        # 1. Fetch current weather forecast
        weather = self.weather_client.get_forecast()
        logger.info(f"Weather: {weather.description}, Temp={weather.temp_c}°C, RainIn3h={weather.rain_expected_next_3h}")

        # 2. Fetch history
        recent_history = self.db.get_recent_readings(hours=12)
        last_pump_event = self.db.get_last_pump_event()
        last_pump_time = None
        if last_pump_event:
            try:
                last_pump_time = datetime.strptime(last_pump_event["timestamp"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        waterings_24h = self.db.get_waterings_in_last_24h()

        # 3. Ask AI LLM for decision
        ai_proposal = self.llm_client.decide(
            current_moisture_pct=self.latest_moisture,
            drum_level=self.latest_drum_level,
            weather=weather,
            recent_history=recent_history,
        )
        logger.info(f"AI Proposed: {ai_proposal.action} (Duration: {ai_proposal.duration_sec}s) | Model: {ai_proposal.model_name}")
        logger.info(f"AI Reasoning: {ai_proposal.reasoning}")

        # 4. Enforce strict code guardrails
        verdict = self.guardrails.evaluate(
            proposed_action=ai_proposal.action,
            proposed_duration_sec=ai_proposal.duration_sec,
            current_moisture_pct=self.latest_moisture,
            drum_level=self.latest_drum_level,
            weather=weather,
            last_pump_time=last_pump_time,
            waterings_in_last_24h=waterings_24h,
        )
        logger.info(f"Guardrail Verdict: {verdict.verdict_type} -> Final Action: {verdict.final_action} ({verdict.final_duration_sec}s)")
        logger.info(f"Guardrail Note: {verdict.reason}")

        # 5. Record decision in SQLite
        weather_summary = f"{weather.description}, {weather.temp_c}°C, Rain3h: {weather.rain_expected_next_3h}"
        self.db.record_decision(
            action=verdict.final_action,
            proposed_duration=ai_proposal.duration_sec,
            approved_duration=verdict.final_duration_sec,
            reasoning=f"AI: {ai_proposal.reasoning} | Policy: {verdict.reason}",
            guardrail_verdict=verdict.verdict_type,
            weather_summary=weather_summary,
            model_used=ai_proposal.model_name,
        )

        # 6. Execute actuation if approved
        if verdict.final_action == "WATER" and verdict.approved:
            self._execute_watering(verdict.final_duration_sec, verdict.reason)

        logger.info("=== IRRIGATION CYCLE COMPLETED ===")

    def _execute_watering(self, duration_sec: int, reason: str):
        """Sends command to ESP32 or logs dry-run, then schedules verification."""
        initial_moisture = self.latest_moisture or 0.0
        event_id = self.db.record_pump_event(
            duration_sec=duration_sec,
            reason=reason,
            trigger_source="AI_AGENT",
            initial_moisture=initial_moisture,
        )

        cmd_payload = {
            "action": "RUN",
            "duration_sec": duration_sec,
            "reason": reason,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

        if config.dry_run:
            logger.info(f"[DRY_RUN MODE] Would publish to {TOPIC_PUMP_COMMAND}: {json.dumps(cmd_payload)}")
        else:
            self.client.publish(TOPIC_PUMP_COMMAND, json.dumps(cmd_payload), qos=1, retain=True)
            logger.info(f"Published pump command to {TOPIC_PUMP_COMMAND}: {json.dumps(cmd_payload)}")

        # Schedule closed-loop moisture verification
        self.pending_verification_event_id = event_id
        self.initial_verification_moisture = initial_moisture
        self.pending_verification_time = datetime.now(timezone.utc) + timedelta(minutes=config.verify_delay_min)
        logger.info(f"Scheduled moisture verification check in {config.verify_delay_min} minutes.")

    def _check_pending_verification(self, current_moisture: float):
        """Verifies that soil moisture actually rose after watering."""
        if not self.pending_verification_event_id or not self.pending_verification_time:
            return

        # Check if verification time has arrived
        if datetime.now(timezone.utc) >= self.pending_verification_time:
            delta = current_moisture - (self.initial_verification_moisture or 0.0)
            logger.info(f"Verification Check: Initial={self.initial_verification_moisture:.1f}%, Current={current_moisture:.1f}%, Delta=+{delta:.1f}%")

            if delta >= 8.0:
                logger.info("CLOSED-LOOP VERIFICATION PASSED: Moisture successfully rose.")
                self.db.update_pump_status(self.pending_verification_event_id, "VERIFIED", verified_moisture=current_moisture)
            else:
                logger.error("CLOSED-LOOP VERIFICATION FAILED: Moisture did not rise after watering!")
                self.db.update_pump_status(self.pending_verification_event_id, "ANOMALY", verified_moisture=current_moisture)
                self.publish_alert("ANOMALY", f"Irrigation ran but moisture did not rise (Delta: {delta:+.1f}%). Check pipe/pump.")

            # Clear pending verification
            self.pending_verification_event_id = None
            self.pending_verification_time = None
            self.initial_verification_moisture = None

    def publish_alert(self, alert_type: str, message: str):
        """Pushes an alert to the dashboard via MQTT."""
        alert_payload = {
            "type": alert_type,
            "message": message,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        self.client.publish(TOPIC_ALERT, json.dumps(alert_payload), qos=1)

    def run(self):
        """Main service loop."""
        logger.info("Starting FarmHub AI Agent Service...")
        try:
            self.client.connect(self.host, self.port, keepalive=config.mqtt_keepalive)
            self.client.loop_start()
        except Exception as e:
            logger.error(f"Could not connect to broker at {self.host}:{self.port}: {e}")
            return

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Service interrupted by user. Stopping...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("FarmHub AI Agent stopped cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Farm Irrigation POC — Python AI Agent Service")
    parser.add_argument("--host", default=config.mqtt_host, help="MQTT Broker host")
    parser.add_argument("--port", type=int, default=config.mqtt_port, help="MQTT Broker port")
    args = parser.parse_args()

    agent = FarmAgentService(host=args.host, port=args.port)
    agent.run()
