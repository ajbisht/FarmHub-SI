"""FarmHub Interactive Edge Node Simulator.

Simulates an ESP32 sending different field telemetry scenarios to test
the ReAct Agent, safety guardrails, and live Command Deck dashboard.
"""

import sys
import time
import urllib.request
import json

BASE_URL = "http://127.0.0.1:8085"

SCENARIOS = {
    "1": {
        "name": "Normal Healthy Soil (38% Moisture, Tank Full)",
        "payload": {
            "soil_moisture_vwc_pct": 38.4,
            "soil_raw_adc": 2150,
            "reservoir_level_ok": True,
            "pump_running": False,
            "cooldown_remaining_sec": 0,
            "total_cycles_today": 1,
            "delivery_verified": True,
            "delivery_fault": False,
            "rssi_dbm": -55
        }
    },
    "2": {
        "name": "Thirsty Soil with Clear Skies (18% Moisture -> Should Water)",
        "payload": {
            "soil_moisture_vwc_pct": 18.2,
            "soil_raw_adc": 2980,
            "reservoir_level_ok": True,
            "pump_running": False,
            "cooldown_remaining_sec": 0,
            "total_cycles_today": 1,
            "delivery_verified": True,
            "delivery_fault": False,
            "rssi_dbm": -58
        }
    },
    "3": {
        "name": "Empty Water Reservoir (Tank Empty -> Safety Block)",
        "payload": {
            "soil_moisture_vwc_pct": 16.5,
            "soil_raw_adc": 3050,
            "reservoir_level_ok": False,
            "pump_running": False,
            "cooldown_remaining_sec": 0,
            "total_cycles_today": 1,
            "delivery_verified": True,
            "delivery_fault": False,
            "rssi_dbm": -52
        }
    },
    "4": {
        "name": "Active Cooldown (Watered 20m ago -> Cooldown Block)",
        "payload": {
            "soil_moisture_vwc_pct": 22.0,
            "soil_raw_adc": 2750,
            "reservoir_level_ok": True,
            "pump_running": False,
            "cooldown_remaining_sec": 3600, # 60m left
            "total_cycles_today": 2,
            "delivery_verified": True,
            "delivery_fault": False,
            "rssi_dbm": -56
        }
    },
    "5": {
        "name": "Delivery Fault (Moisture Didn't Rise -> Pipe Check Alert)",
        "payload": {
            "soil_moisture_vwc_pct": 19.0,
            "soil_raw_adc": 2920,
            "reservoir_level_ok": True,
            "pump_running": False,
            "cooldown_remaining_sec": 0,
            "total_cycles_today": 2,
            "delivery_verified": False,
            "delivery_fault": True,
            "rssi_dbm": -60
        }
    }
}

def send_scenario(scenario_key: str):
    if scenario_key not in SCENARIOS:
        print(f"Unknown scenario '{scenario_key}'")
        return

    sc = SCENARIOS[scenario_key]
    print(f"\n[Simulator] Injecting Scenario {scenario_key}: {sc['name']}...")

    # 1. Post Telemetry
    req = urllib.request.Request(
        f"{BASE_URL}/api/telemetry",
        data=json.dumps(sc["payload"]).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        print(f" -> Telemetry Ingested: Status {resp.status}")

    # 2. Trigger ReAct Agent Evaluation
    eval_req = urllib.request.Request(f"{BASE_URL}/api/evaluate-now", data=b"{}")
    with urllib.request.urlopen(eval_req) as resp:
        result = json.loads(resp.read().decode())
        print(f" -> Agent Decision: {result['agent_verdict']['proposed_action']}")
        print(f" -> Safety Authorized: {result['agent_verdict']['authorized']}")
        print(f" -> Field Agronomist Says: \"{result['field_message']}\"")
        print(f" -> Tools Invoked: {[t['tool'] for t in result['tool_calls_trace']]}")

if __name__ == "__main__":
    choice = sys.argv[1] if len(sys.argv) > 1 else "1"
    send_scenario(choice)
