// FarmHub Irrigation — Mobile Dashboard Client

let ws = null;
let chart = null;
const CIRCUMFERENCE = 565; // 2 * PI * 90

// DOM Elements
const connectionBadge = document.getElementById("connectionBadge");
const connectionText = document.getElementById("connectionText");
const alertBanner = document.getElementById("alertBanner");
const alertMessage = document.getElementById("alertMessage");
const gaugeProgress = document.getElementById("gaugeProgress");
const moistureValue = document.getElementById("moistureValue");
const drumBadge = document.getElementById("drumBadge");
const drumValue = document.getElementById("drumValue");
const pumpBadge = document.getElementById("pumpBadge");
const pumpValue = document.getElementById("pumpValue");
const batteryValue = document.getElementById("batteryValue");
const adcValue = document.getElementById("adcValue");
const btnWater = document.getElementById("btnWater");
const btnStop = document.getElementById("btnStop");
const aiActionTag = document.getElementById("aiActionTag");
const aiReasoningText = document.getElementById("aiReasoningText");

// Initialize Chart.js
function initChart() {
  const ctx = document.getElementById("moistureChart").getContext("2d");
  chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Soil Moisture (%)",
          data: [],
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.1)",
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(15, 23, 42, 0.9)",
          titleColor: "#94a3b8",
          bodyColor: "#f8fafc",
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#64748b", font: { size: 10 } },
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#64748b", font: { size: 10 } },
        },
      },
    },
  });
}

// Update Moisture Gauge
function updateGauge(pct) {
  const clamped = Math.max(0, Math.min(100, pct));
  moistureValue.textContent = clamped.toFixed(1);

  const offset = CIRCUMFERENCE - (clamped / 100) * CIRCUMFERENCE;
  gaugeProgress.style.strokeDashoffset = offset;

  // Dynamically color code the gauge:
  // Red for dry (< 30%), Green for healthy (30-65%), Blue for saturated (> 65%)
  if (clamped < 30) {
    gaugeProgress.style.stroke = "#ef4444";
  } else if (clamped <= 65) {
    gaugeProgress.style.stroke = "#10b981";
  } else {
    gaugeProgress.style.stroke = "#06b6d4";
  }
}

// Update State in UI
function updateUI(state) {
  if (state.moisture_pct !== undefined && state.moisture_pct > 0) {
    updateGauge(state.moisture_pct);
  }

  if (state.raw_adc !== undefined && state.raw_adc > 0) {
    adcValue.textContent = state.raw_adc;
  }

  if (state.battery_v !== undefined) {
    batteryValue.textContent = `${state.battery_v.toFixed(1)}V`;
  }

  // Drum status
  if (state.drum_level) {
    drumValue.textContent = state.drum_level;
    if (state.drum_level === "LOW") {
      drumBadge.style.color = "#ef4444";
      alertBanner.classList.add("visible");
      alertMessage.textContent = "Water reservoir is LOW! Refill 50L drum.";
    } else {
      drumBadge.style.color = "#10b981";
      alertBanner.classList.remove("visible");
    }
  }

  // Pump status
  if (state.pump_state) {
    pumpValue.textContent = state.pump_state;
    if (state.pump_state === "RUNNING") {
      pumpBadge.style.color = "#3b82f6";
      btnWater.disabled = true;
    } else {
      pumpBadge.style.color = "#94a3b8";
      btnWater.disabled = false;
    }
  }
}

// Fetch historical data for Chart
async function loadHistory() {
  try {
    const res = await fetch("/api/history?hours=24");
    const data = await res.json();
    if (data.readings && data.readings.length > 0 && chart) {
      chart.data.labels = data.readings.map((r) =>
        r.timestamp.split(" ")[1].substring(0, 5)
      );
      chart.data.datasets[0].data = data.readings.map((r) => r.moisture_pct);
      chart.update();
    }
  } catch (e) {
    console.error("Failed to load history chart data:", e);
  }
}

// Fetch latest AI decisions
async function loadDecisions() {
  try {
    const res = await fetch("/api/decisions?limit=1");
    const data = await res.json();
    if (data.decisions && data.decisions.length > 0) {
      const d = data.decisions[0];
      aiActionTag.textContent = d.action;
      aiActionTag.className = `ai-decision-tag ${d.action}`;
      aiReasoningText.textContent = d.reasoning;
    }
  } catch (e) {
    console.error("Failed to load decisions:", e);
  }
}

// Connect WebSocket
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    connectionBadge.className = "connection-badge connected";
    connectionText.textContent = "Live";
  };

  ws.onclose = () => {
    connectionBadge.className = "connection-badge disconnected";
    connectionText.textContent = "Reconnecting...";
    setTimeout(connectWebSocket, 3000);
  };

  ws.onerror = () => {
    ws.close();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.event === "INITIAL_SNAPSHOT" && msg.state) {
        updateUI(msg.state);
      } else if (msg.event === "FIELD_UPDATE") {
        if (msg.state) updateUI(msg.state);

        // Append live moisture to chart
        if (msg.topic === "farm/soil/moisture" && chart) {
          const nowStr = new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          });
          chart.data.labels.push(nowStr);
          chart.data.datasets[0].data.push(msg.data.moisture_pct);
          if (chart.data.labels.length > 25) {
            chart.data.labels.shift();
            chart.data.datasets[0].data.shift();
          }
          chart.update();
        }

        // Live alert notification
        if (msg.topic === "farm/alert") {
          alertBanner.classList.add("visible");
          alertMessage.textContent = msg.data.message || "Alert received.";
        }
      }
    } catch (e) {
      console.error("WebSocket message parsing error:", e);
    }
  };
}

// Button Listeners
btnWater.addEventListener("click", async () => {
  btnWater.disabled = true;
  btnWater.textContent = "Sending...";
  try {
    const res = await fetch("/api/override/water?duration_sec=30", {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Water command failed.");
    }
  } catch (e) {
    alert("Network error sending water command.");
  } finally {
    btnWater.disabled = false;
    btnWater.textContent = "💧 Water 30s Now";
  }
});

btnStop.addEventListener("click", async () => {
  try {
    await fetch("/api/override/stop", { method: "POST" });
  } catch (e) {
    console.error("Stop command failed:", e);
  }
});

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    if (data.live && data.live.moisture_pct > 0) {
      updateUI(data.live);
    } else if (data.database_latest) {
      updateUI(data.database_latest);
    }
  } catch (e) {
    console.error("Failed to load status:", e);
  }
}

// Periodic data refreshes
window.addEventListener("DOMContentLoaded", () => {
  initChart();
  loadStatus();
  connectWebSocket();
  loadHistory();
  loadDecisions();

  setInterval(loadDecisions, 15000);
});

