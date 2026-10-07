#!/usr/bin/env bash
# ==============================================================================
# FarmHub Autonomous Irrigation — Raspberry Pi Automated Deployment Script
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CURRENT_USER="$(id -un)"

echo "============================================================"
echo " Starting FarmHub Deployment on Raspberry Pi"
echo " Directory: ${REPO_DIR}"
echo " User:      ${CURRENT_USER}"
echo "============================================================"

# 1. Update APT and install required system packages
echo "[1/6] Installing system packages (Mosquitto, Python3, Git)..."
sudo apt-get update -y
sudo apt-get install -y \
    mosquitto \
    mosquitto-clients \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl

# 2. Configure and restart Mosquitto MQTT Broker
echo "[2/6] Configuring Mosquitto MQTT broker..."
sudo cp "${REPO_DIR}/deploy/mosquitto.conf" /etc/mosquitto/conf.d/farmhub.conf
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
echo "Mosquitto is active and listening on port 1883."

# 3. Create Python Virtual Environment
echo "[3/6] Setting up Python virtual environment (.venv)..."
if [ ! -d "${REPO_DIR}/.venv" ]; then
    python3 -m venv "${REPO_DIR}/.venv"
fi
"${REPO_DIR}/.venv/bin/pip" install --upgrade pip
"${REPO_DIR}/.venv/bin/pip" install -r "${REPO_DIR}/requirements.txt"

# 4. Prepare .env configuration file if missing
echo "[4/6] Checking configuration (.env)..."
if [ ! -f "${REPO_DIR}/.env" ]; then
    echo "Creating .env from .env.example..."
    cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
    # On the Pi, MQTT host is localhost
    sed -i 's/MQTT_BROKER_HOST=.*/MQTT_BROKER_HOST=localhost/' "${REPO_DIR}/.env"
    echo "NOTE: Edit ${REPO_DIR}/.env to add your Groq/OpenWeather API keys."
fi

# 5. Install systemd service units
echo "[5/6] Installing systemd services..."
# Update paths and user dynamically based on the actual installation directory
sudo sed -e "s|/home/pi/RasberryPI|${REPO_DIR}|g" \
         -e "s|User=pi|User=${CURRENT_USER}|g" \
         -e "s|Group=pi|Group=${CURRENT_USER}|g" \
         "${REPO_DIR}/deploy/farmhub-agent.service" | sudo tee /etc/systemd/system/farmhub-agent.service > /dev/null

sudo sed -e "s|/home/pi/RasberryPI|${REPO_DIR}|g" \
         -e "s|User=pi|User=${CURRENT_USER}|g" \
         -e "s|Group=pi|Group=${CURRENT_USER}|g" \
         "${REPO_DIR}/deploy/farmhub-dashboard.service" | sudo tee /etc/systemd/system/farmhub-dashboard.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable farmhub-agent.service
sudo systemctl enable farmhub-dashboard.service

sudo systemctl restart farmhub-agent.service
sudo systemctl restart farmhub-dashboard.service

# 6. Verify and display connection URLs
echo "============================================================"
echo " Deployment Complete!"
echo "============================================================"
echo "Active Services:"
sudo systemctl --no-pager status farmhub-agent.service | head -n 3
sudo systemctl --no-pager status farmhub-dashboard.service | head -n 3
echo "------------------------------------------------------------"
IP_ADDR=$(hostname -I | awk '{print $1}')
echo "Dashboard is LIVE at:"
echo "👉 Local:   http://localhost:8000"
echo "👉 Network: http://${IP_ADDR}:8000 (from your phone browser)"
echo "------------------------------------------------------------"
echo "Useful Commands:"
echo "View Agent Logs:     journalctl -u farmhub-agent -f"
echo "View Dashboard Logs: journalctl -u farmhub-dashboard -f"
echo "Restart Services:    sudo systemctl restart farmhub-agent farmhub-dashboard"
echo "============================================================"
