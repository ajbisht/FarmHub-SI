"""FarmHub Autonomous Irrigation - Unified Application Entrypoint.

This is the root entrypoint for Cloud Run and production container runners (Gunicorn + UvicornWorker).
It launches the FastAPI Dashboard server and runs the Autonomous Farm Agent Service
in a resilient background thread.
"""

import os
import sys
import threading
import logging
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from dashboard.server import app, bridge
from agent.main import FarmAgentService
from agent.config import config

logger = logging.getLogger("FarmHubUnified")

# Global reference for clean shutdown
agent_service_instance = None
agent_worker_thread = None


@app.on_event("startup")
def start_unified_agent_service():
    """Starts the Autonomous AI Agent background worker when FastAPI boots."""
    global agent_service_instance, agent_worker_thread
    run_agent = os.getenv("RUN_AGENT", "true").lower() in ("true", "1", "yes")

    if run_agent:
        logger.info("Booting FarmHub Autonomous AI Agent background worker...")
        try:
            agent_service_instance = FarmAgentService(host=bridge.host, port=bridge.port)
            agent_worker_thread = threading.Thread(
                target=agent_service_instance.run,
                name="FarmAgentWorkerThread",
                daemon=True,
            )
            agent_worker_thread.start()
            logger.info("FarmHub AI Agent worker successfully running in background.")
        except Exception as e:
            logger.error(f"Failed to start background agent service: {e}")


@app.on_event("shutdown")
def stop_unified_agent_service():
    """Stops the background worker cleanly during container scale-down."""
    global agent_service_instance
    if agent_service_instance:
        logger.info("Signaling background FarmHub Agent worker to shut down...")
        agent_service_instance.running = False


# Export app for Gunicorn / Uvicorn (e.g. `gunicorn ... main:app`)
__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    logger.info(f"Starting FarmHub Unified Server on http://{host}:{port}")
    uvicorn.run("main:app", host=host, port=port, reload=False)
