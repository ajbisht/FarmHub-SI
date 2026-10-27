"""
FarmHub Balcony POC Simulator — balcony_sim.py
===============================================
Simulates the real ESP32 field node for the 3-pot balcony setup.

  - 3 independent soil moisture sensors (Mooli, Methi, Pot3-TBD)
  - 1 drum float switch (OK / LOW)
  - Posts HTTPS telemetry to the dashboard /api/telemetry every N seconds
  - Listens for pump command in the telemetry response (command field)
  - Provides a local control HTTP API on port 5001 for manual overrides

Usage:
    python simulator/balcony_sim.py
    python simulator/balcony_sim.py --interval 3 --server http://localhost:8080
    python simulator/balcony_sim.py --dry-pot pot1 --drum-low

Control API (once running):
    curl -X POST http://localhost:5001/sim/set-moisture -H "Content-Type: application/json" -d "{\"pot\":\"pot1\",\"value\":15}"
    curl -X POST http://localhost:5001/sim/set-drum     -H "Content-Type: application/json" -d "{\"level\":\"LOW\"}"
    curl http://localhost:5001/sim/state
"""

import argparse
import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [BALCONY-SIM] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("BalconySim")

CAL_DRY = 2800
CAL_WET = 1100


def pct_to_adc(pct: float) -> int:
    clamped = max(0.0, min(100.0, pct))
    raw = CAL_DRY - ((clamped / 100.0) * (CAL_DRY - CAL_WET))
    raw += random.randint(-12, 12)
    return int(raw)


@dataclass
class PotState:
    id: str
    plant: str
    icon: str
    moisture: float
    dry_rate: float
    threshold_min: float
    threshold_max: float


class BalconySimulator:
    DEFAULT_POTS = [
        PotState("pot1", "Mooli (Radish)",    "🌱", moisture=45.0, dry_rate=0.30, threshold_min=25.0, threshold_max=55.0),
        PotState("pot2", "Methi (Fenugreek)", "🌿", moisture=50.0, dry_rate=0.20, threshold_min=30.0, threshold_max=60.0),
        PotState("pot3", "Pot 3 — TBD",       "🪴", moisture=40.0, dry_rate=0.25, threshold_min=25.0, threshold_max=55.0),
    ]

    def __init__(self, server_url="http://localhost:8080", interval=5, dry_pots=None, drum_low=False):
        self.server_url = server_url.rstrip("/")
        self.interval = interval
        self.pots = {p.id: p for p in self.DEFAULT_POTS}
        self.drum_level = "LOW" if drum_low else "OK"
        self.battery_v = 12.2
        self.running = True
        self.is_pumping = False
        self._lock = threading.Lock()
        for pot_id in (dry_pots or []):
            if pot_id in self.pots:
                self.pots[pot_id].moisture = 10.0
                logger.info(f"[CLI] {pot_id} initialised to 10% (DRY)")

    def _tick_physics(self):
        with self._lock:
            for pot in self.pots.values():
                if self.is_pumping:
                    break
                if pot.moisture > 10.0:
                    pot.moisture -= pot.dry_rate + random.uniform(-0.05, 0.05)
                    pot.moisture = max(10.0, pot.moisture)
            self.battery_v -= random.uniform(0.0, 0.001)
            self.battery_v = max(10.5, self.battery_v)

    def _simulate_watering(self, target_pot_id=None, duration_sec=30):
        if self.drum_level == "LOW":
            logger.warning("Pump blocked — drum is LOW!")
            return
        self.is_pumping = True
        logger.info(f"Pump ON (simulated {duration_sec}s) — moisture rising...")
        sim_sleep = max(1, duration_sec // 6)
        time.sleep(sim_sleep)
        with self._lock:
            for pot in self.pots.values():
                if target_pot_id is None or pot.id == target_pot_id:
                    gain = random.uniform(18.0, 28.0)
                    pot.moisture = min(85.0, pot.moisture + gain)
                    logger.info(f"  {pot.plant}: moisture now {pot.moisture:.1f}%")
        self.is_pumping = False
        logger.info("Pump OFF")

    def _build_payload(self) -> dict:
        with self._lock:
            primary = self.pots["pot1"]
            return {
                "node_id":               "balcony-sim-v1",
                "soil_moisture_vwc_pct": round(primary.moisture, 1),
                "soil_raw_adc":          pct_to_adc(primary.moisture),
                "reservoir_level_ok":    self.drum_level == "OK",
                "pump_running":          self.is_pumping,
                "battery_v":             round(self.battery_v, 2),
                "rssi_dbm":              -58 + random.randint(-5, 5),
                "uptime_sec":            int(time.time() % 86400),
                "mode":                  "simulator",
                "sensors": {
                    pot.id: {
                        "plant":         pot.plant,
                        "icon":          pot.icon,
                        "moisture_pct":  round(pot.moisture, 1),
                        "raw_adc":       pct_to_adc(pot.moisture),
                        "threshold_min": pot.threshold_min,
                        "threshold_max": pot.threshold_max,
                        "status": (
                            "DRY" if pot.moisture < pot.threshold_min else
                            "WET" if pot.moisture > pot.threshold_max else "OK"
                        ),
                    }
                    for pot in self.pots.values()
                },
                "drum": {
                    "level":    self.drum_level,
                    "level_ok": self.drum_level == "OK",
                },
                "simulated": True,
                "ts": datetime.now(timezone.utc).isoformat(),
            }

    def _post_telemetry(self) -> str:
        payload = self._build_payload()
        url = f"{self.server_url}/api/telemetry"
        try:
            resp = requests.post(url, json=payload, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            cmd = data.get("command", "IDLE")
            sensors = payload["sensors"]
            logger.info(
                f"Posted | "
                f"pot1={sensors['pot1']['moisture_pct']:.1f}% ({sensors['pot1']['status']}) "
                f"pot2={sensors['pot2']['moisture_pct']:.1f}% ({sensors['pot2']['status']}) "
                f"pot3={sensors['pot3']['moisture_pct']:.1f}% ({sensors['pot3']['status']}) "
                f"| drum={self.drum_level} | cmd={cmd}"
            )
            return cmd
        except requests.exceptions.ConnectionError:
            logger.warning(f"Dashboard not reachable at {url} — retrying next tick")
            return "IDLE"
        except Exception as e:
            logger.error(f"Telemetry POST failed: {e}")
            return "IDLE"

    def run(self):
        logger.info("=" * 60)
        logger.info("FarmHub Balcony Simulator starting up")
        logger.info(f"  Server  : {self.server_url}")
        logger.info(f"  Interval: {self.interval}s")
        logger.info(f"  Pots    : {', '.join(p.plant for p in self.pots.values())}")
        logger.info(f"  Drum    : {self.drum_level}")
        logger.info("=" * 60)
        while self.running:
            self._tick_physics()
            cmd = self._post_telemetry()
            if cmd and cmd not in ("IDLE", ""):
                if not self.is_pumping:
                    threading.Thread(
                        target=self._simulate_watering,
                        kwargs={"duration_sec": 30},
                        daemon=True,
                    ).start()
            time.sleep(self.interval)
        logger.info("Simulator stopped.")

    def set_moisture(self, pot_id: str, value: float) -> str:
        if pot_id not in self.pots:
            return f"Unknown pot: {pot_id}"
        with self._lock:
            self.pots[pot_id].moisture = max(0.0, min(100.0, value))
        logger.info(f"Manual override: {pot_id} moisture -> {value:.1f}%")
        return "ok"

    def set_drum(self, level: str) -> str:
        level = level.upper()
        if level not in ("OK", "LOW"):
            return "level must be OK or LOW"
        self.drum_level = level
        logger.info(f"Manual override: drum -> {level}")
        return "ok"

    def trigger_pump(self, duration_sec=30) -> str:
        if self.is_pumping:
            return "already pumping"
        threading.Thread(
            target=self._simulate_watering,
            kwargs={"duration_sec": duration_sec},
            daemon=True,
        ).start()
        return "ok"

    def get_state(self) -> dict:
        with self._lock:
            return {
                "pots": {
                    pid: {
                        "plant":        p.plant,
                        "moisture_pct": round(p.moisture, 1),
                        "status": (
                            "DRY" if p.moisture < p.threshold_min else
                            "WET" if p.moisture > p.threshold_max else "OK"
                        ),
                    }
                    for pid, p in self.pots.items()
                },
                "drum":       self.drum_level,
                "battery_v":  round(self.battery_v, 2),
                "is_pumping": self.is_pumping,
            }


_sim_ref = None


class ControlAPIHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send_json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/sim/state":
            self._send_json(200, _sim_ref.get_state())
        elif self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        body = self._read_body()
        if self.path == "/sim/set-moisture":
            self._send_json(200, {"status": _sim_ref.set_moisture(body.get("pot",""), float(body.get("value", 45)))})
        elif self.path == "/sim/set-drum":
            self._send_json(200, {"status": _sim_ref.set_drum(body.get("level", "OK"))})
        elif self.path == "/sim/pump":
            self._send_json(200, {"status": _sim_ref.trigger_pump(int(body.get("duration_sec", 30)))})
        elif self.path == "/sim/stop":
            _sim_ref.running = False
            self._send_json(200, {"status": "stopping"})
        else:
            self._send_json(404, {"error": "unknown endpoint"})


def start_control_api(port=5001):
    server = HTTPServer(("localhost", port), ControlAPIHandler)
    logger.info(f"Sim Control API: http://localhost:{port}")
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FarmHub Balcony POC Simulator")
    parser.add_argument("--server",       default="http://localhost:8080")
    parser.add_argument("--interval",     type=int, default=5)
    parser.add_argument("--drum-low",     action="store_true")
    parser.add_argument("--dry-pot",      action="append", dest="dry_pots", metavar="POT_ID")
    parser.add_argument("--control-port", type=int, default=5001)
    args = parser.parse_args()

    sim = BalconySimulator(
        server_url=args.server,
        interval=args.interval,
        dry_pots=args.dry_pots,
        drum_low=args.drum_low,
    )
    _sim_ref = sim

    threading.Thread(target=start_control_api, args=(args.control_port,), daemon=True).start()

    try:
        sim.run()
    except KeyboardInterrupt:
        logger.info("Simulator stopped.")
