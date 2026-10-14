"""FarmHub Realistic Mock Data Generator.

Simulates dynamic soil moisture drying, root water absorption, automated
agentic watering triggers, pump running states, water drum depletion, and real-time
WebSocket updates to the Command Deck UI.
"""

import sys
import time
import math
import random
import urllib.request
import json
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from farmhub import db

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8085"

def run_simulation(duration_seconds: int = 300, tick_interval: float = 2.5):
    print(f"\n[Mock Generator] Starting live agricultural simulation ({duration_seconds}s run)...")
    print("Press Ctrl+C to stop anytime.\n")

    moisture = 38.0
    pre_watering_moisture = 38.0
    drum_liters = 168.0
    battery_v = 12.35
    pump_running = False
    pump_ticks_remaining = 0
    cooldown_remaining_sec = 0
    cycles_today = 1
    delivery_verified = True
    delivery_fault = False

    start_time = time.time()
    tick_count = 0

    while time.time() - start_time < duration_seconds:
        tick_count += 1

        # A. Simulate Dynamics
        if pump_running:
            # While watering: moisture rises rapidly, drum level drops
            moisture += random.uniform(2.5, 4.0)
            drum_liters -= 0.5
            battery_v = 12.18 # slight voltage dip under motor load
            pump_ticks_remaining -= 1

            if pump_ticks_remaining <= 0 or moisture >= 48.0:
                pump_running = False
                cooldown_remaining_sec = 7200 # 2-hour cooldown
                cycles_today += 1
                delivery_verified = True
                delivery_fault = False
                delta = round(moisture - pre_watering_moisture, 1)
                try:
                    db.log_delivery_event({
                        "duration_sec": 25,
                        "liters_delivered": 3.5,
                        "pre_moisture": round(pre_watering_moisture, 1),
                        "post_moisture": round(moisture, 1),
                        "delta_pct": delta,
                        "verified": True,
                        "delivery_fault": False
                    })
                except Exception as e:
                    pass
                print(f"[{time.strftime('%H:%M:%S')}] [PUMP STOP] Cycle Finished! Moisture reached {moisture:.1f}% (+{delta}% delta). Cooldown active.")
        else:
            # While resting: moisture evaporates gradually
            if cooldown_remaining_sec > 0:
                cooldown_remaining_sec = max(0, cooldown_remaining_sec - 180) # accelerated for demo

            # Natural drying curve
            moisture -= random.uniform(0.3, 0.6)
            battery_v = 12.35 + random.uniform(-0.03, 0.03)

        # Keep moisture bounded
        moisture = max(12.0, min(65.0, moisture))
        drum_liters = max(10.0, min(200.0, drum_liters))

        # Convert moisture to realistic ADC count (higher ADC = drier soil)
        raw_adc = int(3200 - (moisture / 100.0) * (3200 - 1450))

        # Construct Telemetry Payload
        payload = {
            "device_id": "farmhub-node-01",
            "soil_moisture_vwc_pct": round(moisture, 1),
            "soil_raw_adc": raw_adc,
            "reservoir_level_ok": drum_liters > 25.0,
            "pump_running": pump_running,
            "cooldown_remaining_sec": cooldown_remaining_sec,
            "total_cycles_today": cycles_today,
            "delivery_verified": delivery_verified,
            "delivery_fault": delivery_fault,
            "battery_v": round(battery_v, 2),
            "drum_level": {
                "liters": round(drum_liters, 1),
                "pct": round((drum_liters / 200.0) * 100, 1),
                "float_switch_ok": drum_liters > 25.0
            },
            "pump_state": "RUNNING" if pump_running else "IDLE",
            "rssi_dbm": -55 + random.randint(-2, 2)
        }

        # Send Telemetry via HTTP POST
        try:
            req = urllib.request.Request(
                f"{BASE_URL}/api/telemetry",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                pass
        except Exception as e:
            print(f"[Error sending telemetry]: {e}")

        # Every 4 ticks, trigger Agentic AI evaluation
        if tick_count % 4 == 0:
            try:
                eval_req = urllib.request.Request(f"{BASE_URL}/api/evaluate-now", data=b"{}")
                with urllib.request.urlopen(eval_req, timeout=3) as eval_resp:
                    eval_data = json.loads(eval_resp.read().decode())
                    msg = eval_data.get("field_message", "")
                    verdict = eval_data.get("agent_verdict", {})
                    action = verdict.get("proposed_action", "")
                    authorized = verdict.get("authorized", False)
                    dur = verdict.get("authorized_duration_sec", 25)

                    print(f"[{time.strftime('%H:%M:%S')}] [AGENT {action}] \"{msg}\" | Moisture: {moisture:.1f}%")

                    # If Agent orders WATER and not currently running or locked out
                    if action == "WATER" and authorized and not pump_running:
                        pre_watering_moisture = moisture
                        pump_running = True
                        pump_ticks_remaining = max(3, int(dur / tick_interval))
                        print(f"[{time.strftime('%H:%M:%S')}] [PUMP ACTIVATED BY AGENT] Running pump for {dur}s...")
            except Exception as e:
                pass

        time.sleep(tick_interval)

if __name__ == "__main__":
    dur = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    run_simulation(duration_seconds=dur)
