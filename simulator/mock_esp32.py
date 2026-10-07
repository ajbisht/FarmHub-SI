import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path to access agent/config.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.config import (
    TOPIC_DRUM_LEVEL,
    TOPIC_PUMP_ACK,
    TOPIC_PUMP_COMMAND,
    TOPIC_SOIL_MOISTURE,
    TOPIC_STATUS_HEARTBEAT,
    config,
)

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MOCK-ESP32] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("MockESP32")


class MockESP32FieldNode:
    """Simulates the physical ESP32 field controller and its attached sensors:

    - Capacitive Soil Moisture Sensor (Analog ADC mapping)
    - Float switch (OK vs LOW)
    - amiciFlo 12V Submersible Pump (controlled by relay)
    - Battery voltage monitoring
    """

    # ADC calibration curve: Dry Air = 2800 (0%), Water = 1100 (100%)
    CAL_DRY = 2800
    CAL_WET = 1100

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        interval: int = 5,
        initial_moisture: float = 35.0,
        drum_low: bool = False,
    ):
        self.host = host
        self.port = port
        self.interval = interval
        self.moisture_pct = initial_moisture
        self.drum_level = "LOW" if drum_low else "OK"
        self.battery_v = 12.2
        self.is_pumping = False
        self.running = True

        # Initialize MQTT client with compatibility for paho-mqtt v1 and v2
        try:
            self.client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2,
                client_id="mock_esp32_field_node",
            )
        except AttributeError:
            self.client = mqtt.Client(client_id="mock_esp32_field_node")

        self._setup_callbacks()

    def _setup_callbacks(self):
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            logger.info(
                f"Successfully connected to MQTT Broker at {self.host}:{self.port}"
            )
            # Subscribe to pump actuation commands from the agent
            self.client.subscribe(TOPIC_PUMP_COMMAND, qos=1)
            logger.info(f"Subscribed to topic: {TOPIC_PUMP_COMMAND}")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code {rc}")

    def _on_disconnect(self, client, userdata, rc, *args):
        logger.warning(f"Disconnected from MQTT broker (rc: {rc})")

    def _on_message(self, client, userdata, msg):
        """Handle incoming pump commands from the AI Agent."""
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.info(f"Received message on {msg.topic}: {payload}")

            if msg.topic == TOPIC_PUMP_COMMAND:
                action = payload.get("action", "")
                duration_sec = payload.get("duration_sec", 30)
                reason = payload.get("reason", "Manual/AI request")

                if action == "RUN":
                    self._execute_pump(duration_sec, reason)
                elif action == "STOP":
                    logger.info("Emergency STOP command received! Pump halted.")
                    self.is_pumping = False

        except json.JSONDecodeError:
            logger.error(
                f"Malformed JSON payload on {msg.topic}: {msg.payload}"
            )

    def _execute_pump(self, duration_sec: int, reason: str):
        """Simulates running the pump:

        - Closes relay
        - Waits duration
        - Soil moisture rises
        - Sends pump ack
        """
        if self.drum_level == "LOW":
            logger.warning(
                "HARDWARE SAFETY: Pump command ignored because drum level is LOW!"
            )
            return

        logger.info(
            f"Relay activated (GPIO25 HIGH) -> Pump RUNNING for {duration_sec}s. Reason: {reason}"
        )
        self.is_pumping = True

        # Simulate pump runtime
        # (In test simulator, we simulate in 1/5th time so user doesn't wait 30s)
        sim_duration = max(1, duration_sec // 5)
        time.sleep(sim_duration)

        # Moisture rises after watering
        moisture_gain = random.uniform(22.0, 30.0)
        self.moisture_pct = min(85.0, self.moisture_pct + moisture_gain)
        self.is_pumping = False

        logger.info(
            f"Relay deactivated (GPIO25 LOW) -> Pump STOPPED. Moisture rose to {self.moisture_pct:.1f}%"
        )

        # Publish acknowledgement back to agent
        ack_payload = {
            "action": "COMPLETED",
            "duration_sec": duration_sec,
            "simulated": True,
            "ts": datetime.now().isoformat(),
        }
        self.client.publish(
            TOPIC_PUMP_ACK, json.dumps(ack_payload), qos=1, retain=False
        )
        logger.info(
            f"Published ACK to {TOPIC_PUMP_ACK}: {json.dumps(ack_payload)}"
        )

    def _pct_to_raw_adc(self, pct: float) -> int:
        """Converts moisture percentage (0-100) to inverted ESP32 raw ADC value (2800-1100)."""
        clamped_pct = max(0.0, min(100.0, pct))
        raw = self.CAL_DRY - (
            (clamped_pct / 100.0) * (self.CAL_DRY - self.CAL_WET)
        )
        # Add a tiny sensor jitter (+- 15 ADC counts)
        raw += random.randint(-15, 15)
        return int(raw)

    def run(self):
        """Main simulator loop: publishes sensor telemetry every N seconds."""
        logger.info(
            f"Starting Mock ESP32 Field Node (publishing every {self.interval}s)..."
        )
        logger.info(
            f"Initial state: Soil Moisture = {self.moisture_pct:.1f}%, Drum = {self.drum_level}"
        )

        try:
            self.client.connect(self.host, self.port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            logger.error(
                f"Could not connect to broker at {self.host}:{self.port}. Is Mosquitto running?"
            )
            logger.error(f"Details: {e}")
            logger.info("Tip: You can start a local broker or use a test host.")
            return

        try:
            while self.running:
                # 1. Soil naturally dries out slowly over time
                if not self.is_pumping and self.moisture_pct > 18.0:
                    self.moisture_pct -= random.uniform(0.1, 0.4)

                # 2. Publish Soil Moisture
                raw_adc = self._pct_to_raw_adc(self.moisture_pct)
                moisture_payload = {
                    "moisture_pct": round(self.moisture_pct, 1),
                    "raw": raw_adc,
                    "simulated": True,
                    "ts": datetime.now().isoformat(),
                }
                self.client.publish(
                    TOPIC_SOIL_MOISTURE, json.dumps(moisture_payload), qos=1
                )

                # 3. Publish Drum Level
                drum_payload = {
                    "level": self.drum_level,
                    "simulated": True,
                    "ts": datetime.now().isoformat(),
                }
                self.client.publish(
                    TOPIC_DRUM_LEVEL, json.dumps(drum_payload), qos=1
                )

                # 4. Publish Heartbeat / Battery
                heartbeat_payload = {
                    "battery_v": round(self.battery_v, 2),
                    "rssi": -60 + random.randint(-5, 5),
                    "simulated": True,
                    "ts": datetime.now().isoformat(),
                }
                self.client.publish(
                    TOPIC_STATUS_HEARTBEAT, json.dumps(heartbeat_payload), qos=1
                )

                logger.info(
                    f"Telemetric Broadcast: Moisture={self.moisture_pct:.1f}% (ADC {raw_adc}) | Drum={self.drum_level} | Batt={self.battery_v}V"
                )

                time.sleep(self.interval)

        except KeyboardInterrupt:
            logger.info("Simulator interrupted by user. Shutting down...")
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("Mock ESP32 disconnected cleanly.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Autonomous Farm Irrigation POC — Mock ESP32 Field Node"
    )
    parser.add_argument(
        "--host",
        default=config.mqtt_host,
        help="MQTT Broker hostname (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.mqtt_port,
        help="MQTT Broker port (default: 1883)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Telemetry publish interval in seconds (default: 5s)",
    )
    parser.add_argument(
        "--initial-moisture",
        type=float,
        default=32.0,
        help="Initial soil moisture percentage (default: 32%%)",
    )
    parser.add_argument(
        "--drum-low",
        action="store_true",
        help="Start with drum float level = LOW",
    )

    args = parser.parse_args()
    node = MockESP32FieldNode(
        host=args.host,
        port=args.port,
        interval=args.interval,
        initial_moisture=args.initial_moisture,
        drum_low=args.drum_low,
    )
    node.run()
