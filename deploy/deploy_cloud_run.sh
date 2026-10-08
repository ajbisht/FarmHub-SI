#!/usr/bin/env bash
# ==============================================================================
# FarmHub Autonomous Irrigation — Google Cloud Run Deployment Script (Bash)
# Deploys a dedicated, low-cost (Free Tier) Cloud Run service: "farmhub-agent"
# ==============================================================================

set -e

SERVICE_NAME="${1:-farmhub-agent}"
REGION="${2:-asia-south1}"
MQTT_HOST="${3:-broker.hivemq.com}"
MQTT_PORT="${4:-1883}"

echo "================================================================="
echo "🌾 FarmHub AI — Deploying to Google Cloud Run"
echo "Service Name : ${SERVICE_NAME}"
echo "Target Region: ${REGION}"
echo "Public MQTT  : ${MQTT_HOST}:${MQTT_PORT}"
echo "================================================================="

CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null || echo "None")
echo "Active GCP Project: ${CURRENT_PROJECT}"

# Read API keys from environment if set
GROQ_KEY="${GROQ_API_KEY:-}"
OPENAI_KEY="${OPENAI_API_KEY:-}"
WEATHER_KEY="${OPENWEATHER_API_KEY:-}"
PROVIDER="${LLM_PROVIDER:-groq}"

ENV_VARS="MQTT_BROKER_HOST=${MQTT_HOST},MQTT_BROKER_PORT=${MQTT_PORT},LLM_PROVIDER=${PROVIDER},RUN_AGENT=true"
if [ -n "${GROQ_KEY}" ]; then ENV_VARS="${ENV_VARS},GROQ_API_KEY=${GROQ_KEY}"; fi
if [ -n "${OPENAI_KEY}" ]; then ENV_VARS="${ENV_VARS},OPENAI_API_KEY=${OPENAI_KEY}"; fi
if [ -n "${WEATHER_KEY}" ]; then ENV_VARS="${ENV_VARS},OPENWEATHER_API_KEY=${WEATHER_KEY}"; fi

echo "Submitting build and deploying to Cloud Run..."

gcloud run deploy "${SERVICE_NAME}" \
    --source . \
    --region "${REGION}" \
    --platform managed \
    --allow-unauthenticated \
    --min-instances 0 \
    --max-instances 2 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "${ENV_VARS}"

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format="value(status.url)")
echo "================================================================="
echo "✅ DEPLOYMENT SUCCESSFUL!"
echo "🌐 Live Mobile Dashboard: ${SERVICE_URL}"
echo "================================================================="
