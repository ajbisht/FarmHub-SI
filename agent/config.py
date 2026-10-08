import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root if present
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ==============================================================================
# MQTT TOPIC CONSTANTS (The Contract between Field ESP32, Agent, and Dashboard)
# ==============================================================================
TOPIC_SOIL_MOISTURE = "farm/soil/moisture"       # ESP32 -> Agent: {"moisture_pct": 32, "raw": 1950, "ts": ...}
TOPIC_DRUM_LEVEL = "farm/drum/level"             # ESP32 -> Agent: {"level": "OK"|"LOW", "ts": ...}
TOPIC_PUMP_COMMAND = "farm/pump/command"         # Agent -> ESP32: {"action": "RUN", "duration_sec": 30, "reason": "..."}
TOPIC_PUMP_ACK = "farm/pump/ack"                 # ESP32 -> Agent: {"action": "COMPLETED", "duration_sec": 30, "ts": ...}
TOPIC_STATUS_HEARTBEAT = "farm/status/heartbeat" # ESP32 -> Agent: {"battery_v": 12.1, "rssi": -65, "ts": ...}
TOPIC_ALERT = "farm/alert"                       # Agent -> UI:    {"type": "LOW_DRUM"|"ANOMALY", "message": "...", "ts": ...}


@dataclass(frozen=True)
class Settings:
    # Broker
    mqtt_host: str = os.getenv("MQTT_BROKER_HOST", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_BROKER_PORT", "1883"))
    mqtt_username: str = os.getenv("MQTT_USERNAME", "")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "")
    mqtt_keepalive: int = int(os.getenv("MQTT_KEEPALIVE_SEC", "60"))

    # Location
    latitude: float = float(os.getenv("LATITUDE", "28.67"))
    longitude: float = float(os.getenv("LONGITUDE", "77.45"))
    location_name: str = os.getenv("LOCATION_NAME", "Ghaziabad, IN")

    # Weather API
    openweather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "")

    # LLM Provider Selection: "groq" | "openai" | "anthropic" | "gemini" | "ollama" | "local"
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq").lower()

    # Provider 1: Groq
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # Provider 2: OpenAI
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Provider 3: Anthropic
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-20241022")

    # Provider 4: Google Gemini
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

    # Provider 5: Local Ollama
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2")

    # Timings (Minutes)
    sense_interval_min: int = int(os.getenv("SENSE_INTERVAL_MIN", "2"))
    verify_delay_min: int = int(os.getenv("VERIFY_DELAY_MIN", "15"))

    # Guardrails
    max_pump_seconds: int = int(os.getenv("MAX_PUMP_SECONDS", "45"))
    min_hours_between_waterings: float = float(os.getenv("MIN_HOURS_BETWEEN_WATERINGS", "2.0"))
    max_waterings_per_day: int = int(os.getenv("MAX_WATERINGS_PER_DAY", "4"))
    max_safe_moisture_pct: float = float(os.getenv("MAX_SAFE_MOISTURE_PCT", "70.0"))

    # Operational Mode
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    # Storage
    db_path: Path = ROOT_DIR / os.getenv("SQLITE_DB_PATH", "farm_irrigation.db")


# Global singleton settings instance
config = Settings()
