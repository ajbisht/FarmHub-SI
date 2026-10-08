# ==============================================================================
# FarmHub Autonomous Irrigation - Google Cloud Run Deployment Script (PowerShell)
# Deploys a dedicated, low-cost (Free Tier) Cloud Run service: "farmhub-agent"
# ==============================================================================

param (
    [string]$ServiceName = "farmhub-agent",
    [string]$Region = "asia-south1",
    [string]$MqttHost = "broker.hivemq.com",
    [int]$MqttPort = 1883
)

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "[FarmHub AI] Deploying to Google Cloud Run" -ForegroundColor Cyan
Write-Host "Service Name : $ServiceName" -ForegroundColor White
Write-Host "Target Region: $Region" -ForegroundColor White
Write-Host "Public MQTT  : ${MqttHost}:${MqttPort}" -ForegroundColor White
Write-Host "=================================================================" -ForegroundColor Cyan

# Check if gcloud is installed
if (-not (Get-Command "gcloud" -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: 'gcloud' CLI is not found on PATH. Please install Google Cloud SDK." -ForegroundColor Red
    exit 1
}

$CurrentProject = gcloud config get-value project 2>$null
Write-Host "Active GCP Project: $CurrentProject" -ForegroundColor Yellow

# Parse .env file if present in project root
$EnvFile = Join-Path (Split-Path $PSScriptRoot -Parent) ".env"
if (Test-Path $EnvFile) {
    Write-Host "Loading credentials from .env..." -ForegroundColor Gray
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if (-not [string]::IsNullOrEmpty($v) -and -not $v.StartsWith("your_")) {
                [Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
}

# Read API keys from environment
$GroqKey = if ($env:GROQ_API_KEY) { $env:GROQ_API_KEY } else { "" }
$OpenAIKey = if ($env:OPENAI_API_KEY) { $env:OPENAI_API_KEY } else { "" }
$WeatherKey = if ($env:OPENWEATHER_API_KEY) { $env:OPENWEATHER_API_KEY } else { "" }
$Provider = if ($env:LLM_PROVIDER) { $env:LLM_PROVIDER } else { "groq" }

# Build environment variables string
$EnvVars = "MQTT_BROKER_HOST=$MqttHost,MQTT_BROKER_PORT=$MqttPort,LLM_PROVIDER=$Provider,RUN_AGENT=true"
if ($GroqKey) { $EnvVars += ",GROQ_API_KEY=$GroqKey" }
if ($OpenAIKey) { $EnvVars += ",OPENAI_API_KEY=$OpenAIKey" }
if ($WeatherKey) { $EnvVars += ",OPENWEATHER_API_KEY=$WeatherKey" }

Write-Host ""
Write-Host "Submitting build and deploying to Cloud Run..." -ForegroundColor Green

& gcloud run deploy $ServiceName `
    --source . `
    --region $Region `
    --platform managed `
    --allow-unauthenticated `
    --min-instances 0 `
    --max-instances 2 `
    --memory 512Mi `
    --cpu 1 `
    --set-env-vars $EnvVars

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=================================================================" -ForegroundColor Green
    Write-Host "[SUCCESS] Cloud Run deployment completed successfully!" -ForegroundColor Green
    $ServiceUrl = gcloud run services describe $ServiceName --region $Region --format="value(status.url)"
    Write-Host "Live URL: $ServiceUrl" -ForegroundColor Cyan
    Write-Host "=================================================================" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "[ERROR] Deployment failed with exit code $LASTEXITCODE. Check output above." -ForegroundColor Red
}
