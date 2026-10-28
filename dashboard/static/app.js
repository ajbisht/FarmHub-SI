// ==========================================================================
// FarmHub Mission Control — Live Dashboard Client & Telemetry Engine
// ==========================================================================

let ws = null;
let chart = null;
const CIRCUMFERENCE = 565.48; // 2 * Math.PI * 90
let lastMoisturePct = 38.4;
let activePresetKey = "tomatoes";

// Built-in Crop Presets (Fallback if crops_config.json fails to load)
const DEFAULT_CROP_PRESETS = {
  tomatoes: {
    id: "tomatoes",
    title: "Terrace Bed: 5 Tomato Plants",
    badge: "5 Plants",
    icon: "🍅",
    description: "5-Plant High-Altitude Drip Pilot in Polyhouse Bed",
    target_min: 25,
    target_max: 55,
    plants: [
      { id: "p1", name: "Cherokee Purple", variety: "Heirloom Beefsteak", icon: "🍅", offset: -0.6 },
      { id: "p2", name: "Roma Plum", variety: "Paste / Sauce", icon: "🍅", offset: 0.4 },
      { id: "p3", name: "San Marzano", variety: "Italian Plum", icon: "🍅", offset: 1.8 },
      { id: "p4", name: "Beefsteak Heritage", variety: "Large Red", icon: "🍅", offset: -1.2 },
      { id: "p5", name: "Cherry Sweet", variety: "Saladette Cluster", icon: "🍅", offset: 0.2 },
    ],
  },
  avocado: {
    id: "avocado",
    title: "Highland Avocado Trees",
    badge: "4 Trees",
    icon: "🥑",
    description: "Sub-Himalayan Cold-Tolerant Hass & Fuerte Orchard",
    target_min: 28,
    target_max: 60,
    plants: [
      { id: "p1", name: "Hass Graft Tree #1", variety: "Dwarf Perennial", icon: "🥑", offset: -0.8 },
      { id: "p2", name: "Hass Graft Tree #2", variety: "Dwarf Perennial", icon: "🥑", offset: 0.5 },
      { id: "p3", name: "Fuerte Type A #3", variety: "Cold-Hardy Valley", icon: "🥑", offset: 1.4 },
      { id: "p4", name: "Fuerte Type B #4", variety: "Cold-Hardy Valley", icon: "🥑", offset: -0.3 },
    ],
  },
  lime: {
    id: "lime",
    title: "Kagzi Lime Bio-Fence",
    badge: "6 Bushes",
    icon: "🍋",
    description: "Terrace Perimeter Monkey-Proof Citrus Border",
    target_min: 20,
    target_max: 50,
    plants: [
      { id: "p1", name: "North Lime Bush #1", variety: "Citrus aurantifolia", icon: "🍋", offset: -0.5 },
      { id: "p2", name: "North Lime Bush #2", variety: "Citrus aurantifolia", icon: "🍋", offset: 0.3 },
      { id: "p3", name: "Mid-Terrace Bush #3", variety: "Citrus aurantifolia", icon: "🍋", offset: 0.9 },
      { id: "p4", name: "South Lime Bush #4", variety: "Citrus aurantifolia", icon: "🍋", offset: -1.0 },
      { id: "p5", name: "South Lime Bush #5", variety: "Citrus aurantifolia", icon: "🍋", offset: 0.4 },
      { id: "p6", name: "Gate Perimeter Bush #6", variety: "Citrus aurantifolia", icon: "🍋", offset: 0.1 },
    ],
  },
  turmeric: {
    id: "turmeric",
    title: "Black Turmeric Raised Beds",
    badge: "3 Beds",
    icon: "🌿",
    description: "Wild-Boar Proof High-Value Himalayan Curcuma caesia",
    target_min: 35,
    target_max: 65,
    plants: [
      { id: "p1", name: "Terrace Bed A (Shade)", variety: "Medicinal Rhizome", icon: "🌿", offset: 0.0 },
      { id: "p2", name: "Terrace Bed B (Center)", variety: "Medicinal Rhizome", icon: "🌿", offset: 1.2 },
      { id: "p3", name: "Terrace Bed C (Stream-Side)", variety: "Medicinal Rhizome", icon: "🌿", offset: -0.7 },
    ],
  },
};

let cropPresets = DEFAULT_CROP_PRESETS;

// DOM Elements: Navigation & HUD
const connectionHudPill = document.getElementById("connectionHudPill");
const connectionText = document.getElementById("connectionText");
const navBatteryVal = document.getElementById("navBatteryVal");
const navBatteryPct = document.getElementById("navBatteryPct");
const btnTogglePause = document.getElementById("btnTogglePause");
const pauseIcon = document.getElementById("pauseIcon");
const pauseText = document.getElementById("pauseText");
const btnEvaluateNow = document.getElementById("btnEvaluateNow");
const activeCropBadge = document.getElementById("activeCropBadge");

// DOM Elements: Alert Banner
const alertBanner = document.getElementById("alertBanner");
const alertTitle = document.getElementById("alertTitle");
const alertMessage = document.getElementById("alertMessage");
const alertDismissBtn = document.getElementById("alertDismissBtn");

// DOM Elements: Soil Module & Radial Gauge
const radialProgress = document.getElementById("radialProgress");
const moistureValue = document.getElementById("moistureValue");
const moistureQuickBadge = document.getElementById("moistureQuickBadge");
const moisturePlainEnglish = document.getElementById("moisturePlainEnglish");
const soilStatusBadge = document.getElementById("soilStatusBadge");
const adcValue = document.getElementById("adcValue");
const adcBarFill = document.getElementById("adcBarFill");

// DOM Elements: Plant Canopy
const canopyTitle = document.getElementById("canopyTitle");
const canopySub = document.getElementById("canopySub");
const canopyCountBadge = document.getElementById("canopyCountBadge");
const plantGridContainer = document.getElementById("plantGridContainer");

// DOM Elements: Hydrology & Drum
const drumFluidWrapper = document.getElementById("drumFluidWrapper");
const drumLitersVal = document.getElementById("drumLitersVal");
const drumPctBadge = document.getElementById("drumPctBadge");
const drumBadge = document.getElementById("drumBadge");
const drumFloatState = document.getElementById("drumFloatState");
const autonomyDays = document.getElementById("autonomyDays");

// DOM Elements: Pump Cockpit
const pumpBadge = document.getElementById("pumpBadge");
const flowPipeContainer = document.getElementById("flowPipeContainer");
const flowStatusLabel = document.getElementById("flowStatusLabel");
const btnWater15 = document.getElementById("btnWater15");
const btnWater30 = document.getElementById("btnWater30");
const btnWater60 = document.getElementById("btnWater60");
const btnStop = document.getElementById("btnStop");
const waterDeliveredToday = document.getElementById("waterDeliveredToday");
const cyclesToday = document.getElementById("cyclesToday");

// DOM Elements: AI Brain
const aiActionTag = document.getElementById("aiActionTag");
const aiModelName = document.getElementById("aiModelName");
const aiReasoningText = document.getElementById("aiReasoningText");
const aiTimestamp = document.getElementById("aiTimestamp");
const guardrailVerdict = document.getElementById("guardrailVerdict");
const decisionFeedList = document.getElementById("decisionFeedList");

// DOM Elements: Weather
const weatherTemp = document.getElementById("weatherTemp");
const weatherDesc = document.getElementById("weatherDesc");
const weatherCondition = document.getElementById("weatherCondition");
const rainGaugeFill = document.getElementById("rainGaugeFill");
const rainPctLabel = document.getElementById("rainPctLabel");
const weatherHumidity = document.getElementById("weatherHumidity");
const weatherWind = document.getElementById("weatherWind");

// DOM Elements: Hardware
const hwBatteryV = document.getElementById("hwBatteryV");

// DOM Elements: Chat Drawer
const chatFloatingBtn = document.getElementById("chatFloatingBtn");
const chatDrawer = document.getElementById("chatDrawer");
const chatCloseBtn = document.getElementById("chatCloseBtn");
const chatBackdrop = document.getElementById("chatBackdrop");
const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");

// DOM Elements: Crop Customization Modal
const btnOpenConfigModal = document.getElementById("btnOpenConfigModal");
const cropConfigModal = document.getElementById("cropConfigModal");
const btnCloseModal = document.getElementById("btnCloseModal");
const modalPresetSelect = document.getElementById("modalPresetSelect");
const modalPlantsList = document.getElementById("modalPlantsList");
const btnSavePreset = document.getElementById("btnSavePreset");

// Mode Switcher Buttons
const modeButtons = document.querySelectorAll(".mode-btn");

// ==========================================================================
// 1. INITIALIZATION: CHART.JS (24H TIME-SERIES)
// ==========================================================================

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
          borderColor: "#2ea043",
          backgroundColor: "rgba(46, 160, 67, 0.08)",
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 2.5,
          pointHoverRadius: 6,
          pointBackgroundColor: "#3fb950",
          yAxisID: "y",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#161b22",
          titleColor: "#8b949e",
          bodyColor: "#f0f6fc",
          borderColor: "#30363d",
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          callbacks: {
            label: (context) => `Soil Moisture: ${context.parsed.y.toFixed(1)}%`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: { color: "#6e7681", font: { family: "JetBrains Mono", size: 10 } },
        },
        y: {
          min: 0,
          max: 100,
          grid: { color: "rgba(255, 255, 255, 0.04)" },
          ticks: {
            color: "#6e7681",
            font: { family: "JetBrains Mono", size: 10 },
            callback: (v) => `${v}%`,
          },
        },
      },
    },
  });
}

// ==========================================================================
// 2. CROP CONFIGURATION & DYNAMIC CANOPY GENERATION
// ==========================================================================

async function loadCropsConfig() {
  try {
    const res = await fetch("/static/crops_config.json");
    if (res.ok) {
      const data = await res.json();
      if (data.presets) {
        cropPresets = data.presets;
      }
      if (data.default_preset && cropPresets[data.default_preset]) {
        activePresetKey = data.default_preset;
      }
    }
  } catch (e) {
    console.log("Using built-in crop presets:", e);
  }
  renderPlantCanopy(activePresetKey);
}

function renderPlantCanopy(presetKey) {
  const preset = cropPresets[presetKey] || cropPresets.tomatoes;
  activePresetKey = presetKey;

  // Update header badge and titles
  if (activeCropBadge) {
    activeCropBadge.textContent = `TERRACE DRIP • ${preset.badge ? preset.badge.toUpperCase() : "MONITORED"}`;
  }
  if (canopyTitle) {
    canopyTitle.textContent = preset.title;
  }
  if (canopySub) {
    canopySub.textContent = preset.description || "Live plant hydration simulation";
  }
  if (canopyCountBadge) {
    canopyCountBadge.textContent = `${preset.plants.length} Active Plants`;
  }

  // Build plant cards
  if (plantGridContainer) {
    plantGridContainer.innerHTML = preset.plants
      .map(
        (p) => `
        <div class="plant-card" id="plantCard_${p.id}">
          <div class="plant-card-top">
            <div class="plant-icon-num">
              <span class="plant-emoji">${p.icon || "🌱"}</span>
              <span class="plant-num">${p.id.toUpperCase()}</span>
            </div>
            <span class="plant-dot dot-optimal" id="${p.id}Dot"></span>
          </div>
          <span class="plant-name" title="${p.name}">${p.name}</span>
          <span class="plant-variety" title="${p.variety || ""}">${p.variety || ""}</span>
          <div class="plant-footer">
            <span class="plant-pct mono" id="${p.id}Moisture">--%</span>
            <span class="plant-status-text" id="${p.id}Status">Good</span>
          </div>
        </div>
      `
      )
      .join("");
  }

  // Update active pill styling
  document.querySelectorAll(".crop-tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("data-preset") === presetKey);
  });

  // Re-run moisture calculation for newly rendered cards
  updatePlantCanopy(lastMoisturePct);
}

function updatePlantCanopy(basePct) {
  lastMoisturePct = basePct;
  const preset = cropPresets[activePresetKey] || cropPresets.tomatoes;
  const targetMin = preset.target_min || 25;
  const targetMax = preset.target_max || 55;

  preset.plants.forEach((p) => {
    const el = document.getElementById(`${p.id}Moisture`);
    const dot = document.getElementById(`${p.id}Dot`);
    const status = document.getElementById(`${p.id}Status`);

    if (el) {
      const offset = Number(p.offset) || 0;
      const val = Math.max(10, Math.min(95, basePct + offset));
      el.textContent = `${val.toFixed(0)}%`;

      if (val < targetMin || val < 25) {
        if (dot) dot.className = "plant-dot dot-danger";
        if (status) {
          status.textContent = "Thirsty";
          status.style.color = "#ff7b72";
        }
      } else if (val > targetMax || val > 60) {
        if (dot) dot.className = "plant-dot dot-warning";
        if (status) {
          status.textContent = "Wet";
          status.style.color = "#e3b341";
        }
      } else {
        if (dot) dot.className = "plant-dot dot-optimal";
        if (status) {
          status.textContent = "Healthy";
          status.style.color = "#3fb950";
        }
      }
    }
  });
}

// ==========================================================================
// 3. RADIAL GAUGE & SOIL UPDATE (SPACIOUS, NO OVERFLOW)
// ==========================================================================

function updateSoilGauge(pct) {
  const clamped = Math.max(0, Math.min(100, pct));
  moistureValue.textContent = clamped.toFixed(1);

  // SVG Radial stroke offset
  const offset = CIRCUMFERENCE - (clamped / 100) * CIRCUMFERENCE;
  radialProgress.style.strokeDashoffset = offset;

  // Dial Quick Badge & Caption below the circle
  if (clamped < 25) {
    moistureQuickBadge.textContent = "Thirsty";
    moistureQuickBadge.className = "radial-quick-badge badge-danger";
    soilStatusBadge.textContent = "THIRSTY (<25%)";
    soilStatusBadge.className = "status-pill pill-danger";
    if (moisturePlainEnglish) {
      moisturePlainEnglish.textContent = "Soil is dry. Roots need water soon.";
    }
  } else if (clamped <= 55) {
    moistureQuickBadge.textContent = "Just Right";
    moistureQuickBadge.className = "radial-quick-badge badge-optimal";
    soilStatusBadge.textContent = "JUST RIGHT (25–55%)";
    soilStatusBadge.className = "status-pill pill-optimal";
    if (moisturePlainEnglish) {
      moisturePlainEnglish.textContent = "Soil has healthy, ideal water for roots.";
    }
  } else {
    moistureQuickBadge.textContent = "Wet";
    moistureQuickBadge.className = "radial-quick-badge badge-warning";
    soilStatusBadge.textContent = "WET (>55%)";
    soilStatusBadge.className = "status-pill pill-warning";
    if (moisturePlainEnglish) {
      moisturePlainEnglish.textContent = "Soil is well hydrated. No water needed.";
    }
  }

  // Update Plant Canopy Simulation
  updatePlantCanopy(clamped);
}

// ==========================================================================
// 4. WATER RESERVOIR & DRUM UPDATE
// ==========================================================================

function updateDrumReservoir(data, isLow) {
  let liters = 180.0;
  let pct = 90.0;
  let floatOk = true;

  if (typeof data === "object" && data !== null) {
    if (data.liters !== undefined) liters = Number(data.liters);
    if (data.pct !== undefined) pct = Number(data.pct);
    else pct = (liters / 200.0) * 100;
    if (data.float_switch_ok !== undefined) floatOk = Boolean(data.float_switch_ok);
  } else if (typeof data === "number") {
    liters = Number(data);
    pct = (liters / 200.0) * 100;
  } else if (data === "LOW" || isLow === false) {
    floatOk = false;
    liters = 15.0;
    pct = 7.5;
  }

  if (isLow === false) {
    floatOk = false;
  }

  pct = Math.max(0, Math.min(100, pct));
  const days = Math.max(0, Math.round(liters / 5.5));

  if (!floatOk || liters < 25.0 || pct < 15.0) {
    if (drumBadge) {
      drumBadge.textContent = "WATER LOW";
      drumBadge.className = "status-pill pill-danger";
    }
    if (drumFloatState) {
      drumFloatState.textContent = "Low — Needs Refill";
      drumFloatState.className = "stat-text-bold highlight-rose";
    }
    if (autonomyDays) autonomyDays.textContent = String(Math.max(1, days));
    if (drumPctBadge) drumPctBadge.textContent = `${pct.toFixed(0)}% Full`;
    if (alertBanner) {
      alertBanner.classList.add("visible");
      alertTitle.textContent = "Water Tank Needs Attention";
      alertMessage.textContent = "Water drum is LOW (<25L). Pump cutoff active to protect motor.";
    }
  } else {
    if (drumBadge) {
      drumBadge.textContent = pct > 85 ? "WATER FULL" : "WATER SAFE";
      drumBadge.className = "status-pill pill-optimal";
    }
    if (drumFloatState) {
      drumFloatState.textContent = "Plenty of Water (Safe)";
      drumFloatState.className = "stat-text-bold highlight-green";
    }
    if (autonomyDays) autonomyDays.textContent = String(days);
    if (drumPctBadge) drumPctBadge.textContent = `${pct.toFixed(0)}% Full`;
    if (alertBanner) {
      alertBanner.classList.remove("visible");
    }
  }

  if (drumFluidWrapper) drumFluidWrapper.style.height = `${pct.toFixed(1)}%`;
  if (drumLitersVal) drumLitersVal.textContent = liters.toFixed(1);
}

// ==========================================================================
// 5. PUMP ACTUATOR & FLOW COCKPIT UPDATE
// ==========================================================================

function updatePumpState(pumpState) {
  if (pumpState === "RUNNING") {
    pumpBadge.textContent = "WATERING NOW";
    pumpBadge.className = "status-pill pill-active";
    flowPipeContainer.classList.add("running");
    flowStatusLabel.textContent = "2.2 L/min (Active Drip Flow)";
    btnWater15.disabled = true;
    btnWater30.disabled = true;
    btnWater60.disabled = true;
  } else {
    pumpBadge.textContent = "PUMP RESTING";
    pumpBadge.className = "status-pill pill-idle";
    flowPipeContainer.classList.remove("running");
    flowStatusLabel.textContent = "Pump is Resting (Off)";
    btnWater15.disabled = false;
    btnWater30.disabled = false;
    btnWater60.disabled = false;
  }
}

// ==========================================================================
// 6. BATTERY & HARDWARE HEALTH UPDATE
// ==========================================================================

function updateBattery(volts) {
  const v = Number(volts) || 12.3;
  navBatteryVal.textContent = `${v.toFixed(1)}V`;
  hwBatteryV.textContent = `${v.toFixed(1)}V`;

  // 3S Li-ion percentage: 11.1V = 0%, 12.6V = 100%
  const pct = Math.max(5, Math.min(100, Math.round(((v - 11.1) / (12.6 - 11.1)) * 100)));
  navBatteryPct.textContent = `${pct}% Healthy`;
}

// ==========================================================================
// 7. MASTER UI STATE UPDATE
// ==========================================================================

function updateUI(state) {
  if (!state) return;

  const m = state.soil_moisture_vwc_pct !== undefined ? state.soil_moisture_vwc_pct : state.moisture_pct;
  if (m !== undefined && m !== null && !isNaN(m)) {
    updateSoilGauge(Number(m));
  }

  const adc = state.soil_raw_adc !== undefined ? state.soil_raw_adc : state.raw_adc;
  if (adc !== undefined && adc !== null && !isNaN(adc)) {
    adcValue.textContent = adc;
    const barWidth = Math.min(100, Math.round((Number(adc) / 4095) * 100));
    adcBarFill.style.width = `${barWidth}%`;
  }

  if (state.battery_v !== undefined) {
    updateBattery(state.battery_v);
  }

  if (state.drum_level !== undefined) {
    updateDrumReservoir(state.drum_level, state.reservoir_level_ok);
  } else if (state.drum_liters !== undefined) {
    updateDrumReservoir({
      liters: state.drum_liters,
      pct: state.drum_pct,
      float_switch_ok: state.reservoir_level_ok
    }, state.reservoir_level_ok);
  } else if (state.reservoir_level_ok !== undefined) {
    updateDrumReservoir(state.reservoir_level_ok ? "OK" : "LOW", state.reservoir_level_ok);
  }

  if (state.pump_state) {
    updatePumpState(state.pump_state);
  }

  // Delivery Verification Check
  const deliveryStatusBadge = document.getElementById("deliveryStatusBadge");
  const deliveryStatusSub = document.getElementById("deliveryStatusSub");
  if (deliveryStatusBadge && deliveryStatusSub) {
    if (state.delivery_fault) {
      deliveryStatusBadge.textContent = "⚠️ Check Pipe";
      deliveryStatusBadge.className = "mini-mono highlight-amber";
      deliveryStatusSub.textContent = "Soil didn't rise after pump";
    } else if (state.delivery_verified !== false) {
      deliveryStatusBadge.textContent = "✔ Verified";
      deliveryStatusBadge.className = "mini-mono highlight-green";
      deliveryStatusSub.textContent = "Soil delta healthy";
    }
  }

  // Automation Paused Flag
  if (state.automation_paused !== undefined) {
    if (state.automation_paused) {
      pauseIcon.textContent = "▶";
      pauseText.textContent = "Resume Auto";
      btnTogglePause.style.borderColor = "var(--amber)";
      aiActionTag.textContent = "PAUSED";
      aiActionTag.className = "status-pill pill-warning";
    } else {
      pauseIcon.textContent = "⏸";
      pauseText.textContent = "Pause Auto";
      btnTogglePause.style.borderColor = "var(--border-subtle)";
    }
  }

  // Multi-sensor / Balcony POC update
  updateBalconyState(state);
}

// ==========================================================================
// 8. DATA FETCHING: HISTORY, DECISIONS, STATUS
// ==========================================================================

async function loadHistory() {
  try {
    const res = await fetch("/api/history?hours=24");
    if (!res.ok) return;
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

async function loadDecisions() {
  try {
    const res = await fetch("/api/decisions?limit=5");
    if (!res.ok) return;
    const data = await res.json();
    if (data.decisions && data.decisions.length > 0) {
      const latest = data.decisions[0];
      const isWater = latest.action === "WATER";
      aiActionTag.textContent = isWater ? "WATERED" : "WATCHING SOIL";
      aiActionTag.className = `status-pill ${isWater ? "pill-active" : "pill-ai"}`;
      aiReasoningText.textContent = latest.reasoning || "Autonomous soil & rain monitoring active.";
      if (latest.model_used) {
        aiModelName.textContent = latest.model_used;
      }
      if (latest.guardrail_verdict) {
        guardrailVerdict.textContent = `Safety Rule: ${latest.guardrail_verdict}`;
      }

      // Populate Decision Feed in simple English
      decisionFeedList.innerHTML = data.decisions
        .map(
          (d) => `
        <div class="feed-item">
          <span class="feed-action ${d.action === "WATER" ? "tag-water" : "tag-skip"}">${d.action === "WATER" ? "WATERED" : "NO WATER"}</span>
          <span class="feed-reason" title="${d.reasoning}">${d.reasoning}</span>
          <span class="feed-time">${d.timestamp ? d.timestamp.split(" ")[1].substring(0, 5) : "--"}</span>
        </div>
      `
        )
        .join("");
    }
  } catch (e) {
    console.error("Failed to load decisions:", e);
  }
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (res.ok) {
      const data = await res.json();
      const liveState = data.live || data.telemetry;
      if (liveState) {
        updateUI(liveState);
        if (!ws || ws.readyState !== WebSocket.OPEN) {
          connectionHudPill.style.borderColor = "rgba(46, 160, 67, 0.4)";
          connectionText.textContent = "Connected Live";
        }
      }
      if (data.waterings_24h !== undefined) {
        cyclesToday.textContent = `${data.waterings_24h} Times`;
        const estLiters = (data.waterings_24h * 1.5).toFixed(1);
        waterDeliveredToday.textContent = `${estLiters} Liters`;
      }
    }
  } catch (e) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectionHudPill.style.borderColor = "rgba(248, 81, 73, 0.4)";
      connectionText.textContent = "Offline";
    }
  }
}

// ==========================================================================
// 9. WEBSOCKET REAL-TIME CONNECTION
// ==========================================================================

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  try {
    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      connectionHudPill.style.borderColor = "rgba(46, 160, 67, 0.5)";
      connectionText.textContent = "Connected Live";
    };

    ws.onclose = () => {
      setTimeout(connectWebSocket, 4000);
    };

    ws.onerror = () => {
      if (ws) ws.close();
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.event === "INITIAL_SNAPSHOT" || msg.event === "FIELD_UPDATE" || msg.event === "TELEMETRY_UPDATE" || msg.event === "SIM_UPDATE") {
          updateUI(msg.state);
        }
      } catch (err) {
        console.error("WebSocket message parse error:", err);
      }
    };
  } catch (e) {
    console.warn("WebSocket init error:", e);
  }
}

// ==========================================================================
// 10. MANUAL OVERRIDES: 15S, 30S, 60S, STOP, PAUSE, EVALUATE
// ==========================================================================

async function triggerWater(durationSec) {
  try {
    const res = await fetch(`/api/override/water?duration_sec=${durationSec}`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.detail || "Watering could not start. Please check tank level.");
      return;
    }
    updatePumpState("RUNNING");
    const bpPumpBadge = document.getElementById("bpPumpBadge");
    if (bpPumpBadge) {
      bpPumpBadge.textContent = "RUNNING";
      bpPumpBadge.className = "status-pill pill-active-pump";
    }
  } catch (e) {
    alert("Network error contacting pump.");
  }
}

async function triggerStop() {
  try {
    await fetch("/api/override/stop", { method: "POST" });
    updatePumpState("IDLE");
    const bpPumpBadge = document.getElementById("bpPumpBadge");
    if (bpPumpBadge) {
      bpPumpBadge.textContent = "STOPPED";
      bpPumpBadge.className = "status-pill pill-idle";
    }
  } catch (e) {
    alert("Stop request failed.");
  }
}

async function triggerTogglePause() {
  try {
    const res = await fetch("/api/override/toggle-pause", { method: "POST" });
    const data = await res.json();
    if (data.status === "SUCCESS") {
      updateUI({ automation_paused: data.automation_paused });
    }
  } catch (e) {
    alert("Toggle pause failed.");
  }
}

async function triggerEvaluateNow() {
  btnEvaluateNow.textContent = "⚡ Checking...";
  btnEvaluateNow.disabled = true;
  try {
    const res = await fetch("/api/evaluate-now", { method: "POST" });
    if (res.ok) {
      await loadDecisions();
    }
  } catch (e) {
    console.error("Evaluate now error:", e);
  } finally {
    btnEvaluateNow.textContent = "⚡ Check Now";
    btnEvaluateNow.disabled = false;
  }
}

// ==========================================================================
// 11. CROP CUSTOMIZATION MODAL LOGIC
// ==========================================================================

function openCropConfigModal() {
  if (!cropConfigModal) return;
  modalPresetSelect.value = activePresetKey;
  updateModalPlantsList(activePresetKey);
  cropConfigModal.classList.add("open");
}

function closeCropConfigModal() {
  if (cropConfigModal) {
    cropConfigModal.classList.remove("open");
  }
}

function updateModalPlantsList(presetKey) {
  const preset = cropPresets[presetKey] || cropPresets.tomatoes;
  if (!modalPlantsList) return;
  modalPlantsList.innerHTML = preset.plants
    .map(
      (p) => `
    <div class="modal-plant-row">
      <div class="modal-plant-info">
        <span class="modal-plant-icon">${p.icon || "🌱"}</span>
        <div>
          <div class="modal-plant-name">${p.name}</div>
          <div class="modal-plant-variety">${p.variety || ""}</div>
        </div>
      </div>
      <div class="modal-plant-threshold">
        Target: ${preset.target_min || 25}%–${preset.target_max || 55}%
      </div>
    </div>
  `
    )
    .join("");
}

// ==========================================================================
// 12. CHAT DRAWER & AI COPILOT
// ==========================================================================

function openChat() {
  chatDrawer.classList.add("open");
  chatBackdrop.classList.add("visible");
  chatInput.focus();
}

function closeChat() {
  chatDrawer.classList.remove("open");
  chatBackdrop.classList.remove("visible");
}

function appendChatMessage(sender, text) {
  const isAi = sender === "ai";
  const msgEl = document.createElement("div");
  msgEl.className = `chat-msg ${isAi ? "ai-msg" : "user-msg"}`;
  msgEl.innerHTML = `
    <div class="msg-bubble">${text}</div>
    <span class="msg-time">Just now</span>
  `;
  chatMessages.appendChild(msgEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChatMessage(promptText) {
  const query = promptText || chatInput.value.trim();
  if (!query) return;

  appendChatMessage("user", query);
  chatInput.value = "";

  const thinkingId = `ai_think_${Date.now()}`;
  const thinkingEl = document.createElement("div");
  thinkingEl.id = thinkingId;
  thinkingEl.className = "chat-msg ai-msg";
  thinkingEl.innerHTML = `
    <div class="msg-bubble" style="opacity: 0.7;">Checking farm telemetry...</div>
  `;
  chatMessages.appendChild(thinkingEl);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: query }),
    });
    const data = await res.json();
    thinkingEl.remove();
    appendChatMessage("ai", data.reply || "Telemetry check completed.");
  } catch (e) {
    thinkingEl.remove();
    appendChatMessage(
      "ai",
      "I had trouble contacting the AI server. Please verify your connection."
    );
  }
}

// ==========================================================================
// 13. DOM READY EVENT LISTENERS
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  initChart();
  loadCropsConfig();
  connectWebSocket();

  // Initial polls
  pollStatus();
  loadHistory();
  loadDecisions();

  // Periodic polling
  setInterval(pollStatus, 5000);
  setInterval(loadHistory, 30000);
  setInterval(loadDecisions, 15000);

  // Manual pulse buttons
  btnWater15.addEventListener("click", () => triggerWater(15));
  btnWater30.addEventListener("click", () => triggerWater(30));
  btnWater60.addEventListener("click", () => triggerWater(60));
  btnStop.addEventListener("click", triggerStop);

  // Nav Actions
  btnTogglePause.addEventListener("click", triggerTogglePause);
  btnEvaluateNow.addEventListener("click", triggerEvaluateNow);
  alertDismissBtn.addEventListener("click", () => alertBanner.classList.remove("visible"));

  // Crop Tab Switching Buttons
  document.querySelectorAll(".crop-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const presetKey = btn.getAttribute("data-preset");
      renderPlantCanopy(presetKey);
    });
  });

  // Crop Config Modal Event Listeners
  if (btnOpenConfigModal) {
    btnOpenConfigModal.addEventListener("click", openCropConfigModal);
  }
  if (btnCloseModal) {
    btnCloseModal.addEventListener("click", closeCropConfigModal);
  }
  if (cropConfigModal) {
    cropConfigModal.addEventListener("click", (e) => {
      if (e.target === cropConfigModal) closeCropConfigModal();
    });
  }
  if (modalPresetSelect) {
    modalPresetSelect.addEventListener("change", (e) => {
      updateModalPlantsList(e.target.value);
    });
  }
  if (btnSavePreset) {
    btnSavePreset.addEventListener("click", () => {
      const selected = modalPresetSelect.value;
      renderPlantCanopy(selected);
      closeCropConfigModal();
    });
  }

  // Mode Switcher Buttons
  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
    });
  });

  // Chat Drawer Event Listeners
  chatFloatingBtn.addEventListener("click", openChat);
  chatCloseBtn.addEventListener("click", closeChat);
  chatBackdrop.addEventListener("click", closeChat);

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    sendChatMessage();
  });

  document.querySelectorAll(".chat-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const prompt = chip.getAttribute("data-prompt");
      sendChatMessage(prompt);
    });
  });

  // ==========================================================================
  // 12. TWO-TAB DECK NAVIGATION & SIMULATOR CONTROLS
  // ==========================================================================

  const tabBtnSimulator = document.getElementById("tabBtnSimulator");
  const tabBtnBalcony = document.getElementById("tabBtnBalcony");
  const tabPaneSimulator = document.getElementById("tabPaneSimulator");
  const tabPaneBalcony = document.getElementById("tabPaneBalcony");

  function switchDeckTab(tabName) {
    if (tabName === "simulator") {
      if (tabBtnSimulator) tabBtnSimulator.classList.add("active");
      if (tabBtnBalcony) tabBtnBalcony.classList.remove("active");
      if (tabPaneSimulator) tabPaneSimulator.style.display = "flex";
      if (tabPaneBalcony) tabPaneBalcony.style.display = "none";
    } else if (tabName === "balcony-poc") {
      if (tabBtnBalcony) tabBtnBalcony.classList.add("active");
      if (tabBtnSimulator) tabBtnSimulator.classList.remove("active");
      if (tabPaneBalcony) tabPaneBalcony.style.display = "flex";
      if (tabPaneSimulator) tabPaneSimulator.style.display = "none";
    }
  }

  if (tabBtnSimulator) tabBtnSimulator.addEventListener("click", () => switchDeckTab("simulator"));
  if (tabBtnBalcony) tabBtnBalcony.addEventListener("click", () => switchDeckTab("balcony-poc"));

  // Simulator Control API Proxy caller
  async function sendSimControl(payload) {
    try {
      const res = await fetch("/api/sim/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        console.warn("Simulator control message:", data.detail || data.error);
      }
    } catch (err) {
      console.error("Failed to contact simulator control API:", err);
    }
  }

  // Sim pot override buttons (Dry / Optimal / Wet)
  document.querySelectorAll(".sim-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pot = btn.getAttribute("data-pot");
      const val = parseFloat(btn.getAttribute("data-val") || "45");
      sendSimControl({ action: "set-moisture", pot: pot, value: val });
    });
  });

  // Sim drum level toggle button
  const btnSimToggleDrum = document.getElementById("btnSimToggleDrum");
  if (btnSimToggleDrum) {
    btnSimToggleDrum.addEventListener("click", () => {
      const targetLevel = btnSimToggleDrum.getAttribute("data-level") || "LOW";
      sendSimControl({ action: "set-drum", level: targetLevel });
    });
  }

  // Sim simulate water button
  const btnSimTriggerWater = document.getElementById("btnSimTriggerWater");
  if (btnSimTriggerWater) {
    btnSimTriggerWater.addEventListener("click", () => {
      sendSimControl({ action: "pump", duration_sec: 30 });
    });
  }

  // Balcony POC Quick Water buttons
  document.querySelectorAll(".pot-quick-water-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      triggerWater(15);
    });
  });

  const btnBalconyWaterAll = document.getElementById("btnBalconyWaterAll");
  if (btnBalconyWaterAll) {
    btnBalconyWaterAll.addEventListener("click", () => {
      triggerWater(30);
    });
  }

  const btnBalconyStop = document.getElementById("btnBalconyStop");
  if (btnBalconyStop) {
    btnBalconyStop.addEventListener("click", () => {
      triggerStop();
    });
  }
});

// ==========================================================================
// 13. MULTI-SENSOR & BALCONY POC TELEMETRY RENDERER
// ==========================================================================

function updateBalconyState(state) {
  if (!state) return;
  window.__lastBalconyState = state;

  // 0. Compute Heartbeat & Freshness
  const now = Date.now();
  let isFresh = false;
  if (state.hw_online !== undefined) {
    isFresh = Boolean(state.hw_online);
  } else if (state.last_rx_timestamp) {
    isFresh = (now / 1000 - Number(state.last_rx_timestamp)) < 65;
  } else if (state.last_updated) {
    const t = new Date(state.last_updated.replace(" ", "T")).getTime();
    if (!isNaN(t) && (now - t) < 65000) {
      isFresh = true;
    }
  }

  const isHardware = (state.mode === "hardware") && isFresh;
  const isSim = state.mode === "simulator" || state.sim_running;
  const sensors = state.sensors;

  // 1. Update Hardware/Sim Banner
  const hwBanner = document.getElementById("balconyHwBanner");
  const hwIcon = document.getElementById("balconyHwIcon");
  const hwTitle = document.getElementById("balconyHwTitle");
  const hwDesc = document.getElementById("balconyHwDesc");
  const hwPill = document.getElementById("balconyHwPill");
  const hwLiveBadge = document.getElementById("hwLiveBadge");
  const simLiveBadge = document.getElementById("simLiveBadge");
  const bpPayloadMode = document.getElementById("bpPayloadMode");

  if (hwBanner) {
    if (isHardware) {
      hwBanner.classList.add("hw-connected");
      hwBanner.classList.remove("hw-sim", "hw-offline");
      if (hwIcon) hwIcon.textContent = "🟢";
      if (hwTitle) hwTitle.textContent = "ESP32 Field Node Connected & Streaming";
      if (hwDesc) hwDesc.textContent = "Receiving live physical sensor telemetry directly from your balcony hardware.";
      if (hwPill) {
        hwPill.textContent = "LIVE HARDWARE";
        hwPill.className = "hw-banner-pill live";
      }
      if (hwLiveBadge) {
        hwLiveBadge.textContent = "HW Online";
        hwLiveBadge.className = "tab-badge badge-live";
      }
      if (simLiveBadge) {
        simLiveBadge.textContent = "Sim Inactive";
        simLiveBadge.className = "tab-badge badge-dim";
      }
      if (bpPayloadMode) {
        bpPayloadMode.textContent = "ESP32 Hardware Stream";
        bpPayloadMode.className = "metric-tag tag-active";
      }
    } else if (isSim) {
      hwBanner.classList.remove("hw-connected", "hw-offline");
      hwBanner.classList.add("hw-sim");
      if (hwIcon) hwIcon.textContent = "🧪";
      if (hwTitle) hwTitle.textContent = "Balcony POC Virtual Simulator Active";
      if (hwDesc) hwDesc.textContent = "Currently displaying telemetry from Balcony POC Simulator. Switch on your physical ESP32 to switch to live hardware stream.";
      if (hwPill) {
        hwPill.textContent = "SIMULATED STREAM";
        hwPill.className = "hw-banner-pill";
      }
      if (hwLiveBadge) {
        hwLiveBadge.textContent = "Awaiting HW";
        hwLiveBadge.className = "tab-badge badge-dim";
      }
      if (simLiveBadge) {
        simLiveBadge.textContent = "Sim Active";
        simLiveBadge.className = "tab-badge badge-live";
      }
      if (bpPayloadMode) {
        bpPayloadMode.textContent = "Simulator Stream";
        bpPayloadMode.className = "metric-tag tag-sim";
      }
    } else {
      // Hardware is OFFLINE / Awaiting connection
      hwBanner.classList.remove("hw-connected", "hw-sim");
      hwBanner.classList.add("hw-offline");
      if (hwIcon) hwIcon.textContent = "⚪";
      if (hwTitle) hwTitle.textContent = "Awaiting ESP32 Hardware Connection";
      if (hwDesc) hwDesc.textContent = "No telemetry received recently. Power on your physical ESP32 node to stream live hardware telemetry here.";
      if (hwPill) {
        hwPill.textContent = "HW OFFLINE";
        hwPill.className = "hw-banner-pill offline";
      }
      if (hwLiveBadge) {
        hwLiveBadge.textContent = "HW Offline";
        hwLiveBadge.className = "tab-badge badge-dim";
      }
      if (simLiveBadge) {
        simLiveBadge.textContent = "Sim Inactive";
        simLiveBadge.className = "tab-badge badge-dim";
      }
      if (bpPayloadMode) {
        bpPayloadMode.textContent = "Awaiting ESP32...";
        bpPayloadMode.className = "metric-tag";
      }
    }
  }

  // 2. Helper to update a pot's UI in both Sim Control Strip and Balcony Deck
  function renderPot(potKey, potData, simValId, simBarId, bpMoistId, bpRingId, bpBadgeId, bpAdcId, bpDescId) {
    if (!potData) return;
    const m = Number(potData.moisture_pct || 0);
    const adc = potData.raw_adc !== undefined ? potData.raw_adc : "—";
    const status = potData.status || (m < 25 ? "DRY" : m > 55 ? "WET" : "OK");

    // Sim Strip Updates
    const simVal = document.getElementById(simValId);
    const simBar = document.getElementById(simBarId);
    if (simVal) simVal.textContent = `${m.toFixed(1)}%`;
    if (simBar) simBar.style.width = `${Math.min(100, Math.max(0, m))}%`;

    // Balcony Card Updates
    const bpMoist = document.getElementById(bpMoistId);
    if (bpMoist) bpMoist.textContent = m.toFixed(1);

    const bpRing = document.getElementById(bpRingId);
    if (bpRing) {
      const circ = 339.29; // 2 * PI * 54
      const offset = circ - (m / 100) * circ;
      bpRing.style.strokeDashoffset = Math.max(0, Math.min(circ, offset));
      if (status === "DRY") {
        bpRing.style.stroke = "#ff7b72";
      } else if (status === "WET") {
        bpRing.style.stroke = "#58a6ff";
      } else {
        bpRing.style.stroke = "#3fb950";
      }
    }

    const bpBadge = document.getElementById(bpBadgeId);
    if (bpBadge) {
      if (status === "DRY") {
        bpBadge.textContent = "THIRSTY";
        bpBadge.className = "pot-status-badge badge-dry";
      } else if (status === "WET") {
        bpBadge.textContent = "WATERLOGGED";
        bpBadge.className = "pot-status-badge badge-wet";
      } else {
        bpBadge.textContent = "OPTIMAL";
        bpBadge.className = "pot-status-badge badge-optimal";
      }
    }

    const bpAdc = document.getElementById(bpAdcId);
    if (bpAdc) bpAdc.textContent = `${adc} / 4095`;

    const bpDesc = document.getElementById(bpDescId);
    if (bpDesc) {
      if (status === "DRY") bpDesc.textContent = "Soil is thirsty, roots need water";
      else if (status === "WET") bpDesc.textContent = "Soil is saturated, no water needed";
      else bpDesc.textContent = "Root moisture in sweet spot";
    }
  }

  if (sensors) {
    renderPot("pot1", sensors.pot1, "simPot1Val", "simPot1Bar", "bpPot1Moisture", "bpPot1Ring", "bpPot1Badge", "bpPot1Adc", "bpPot1Desc");
    renderPot("pot2", sensors.pot2, "simPot2Val", "simPot2Bar", "bpPot2Moisture", "bpPot2Ring", "bpPot2Badge", "bpPot2Adc", "bpPot2Desc");
    renderPot("pot3", sensors.pot3, "simPot3Val", "simPot3Bar", "bpPot3Moisture", "bpPot3Ring", "bpPot3Badge", "bpPot3Adc", "bpPot3Desc");
  } else if (state.moisture_pct !== undefined) {
    // If running single-sensor (legacy/hardware), map primary reading to Pot 1
    const singleData = {
      moisture_pct: state.moisture_pct,
      raw_adc: state.raw_adc,
      status: state.moisture_pct < 25 ? "DRY" : state.moisture_pct > 55 ? "WET" : "OK"
    };
    renderPot("pot1", singleData, "simPot1Val", "simPot1Bar", "bpPot1Moisture", "bpPot1Ring", "bpPot1Badge", "bpPot1Adc", "bpPot1Desc");
  }

  // 3. Drum Level Updates
  const drumLevel = state.drum_level || (state.reservoir_level_ok ? "OK" : "LOW");
  const isDrumLow = drumLevel === "LOW";

  const simDrumStatus = document.getElementById("simDrumStatus");
  const btnSimToggleDrum = document.getElementById("btnSimToggleDrum");
  if (simDrumStatus) {
    if (isDrumLow) {
      simDrumStatus.textContent = "● LOW (Empty Tank)";
      simDrumStatus.className = "sim-env-status status-low";
    } else {
      simDrumStatus.textContent = "● OK (Adequate)";
      simDrumStatus.className = "sim-env-status status-ok";
    }
  }
  if (btnSimToggleDrum) {
    if (isDrumLow) {
      btnSimToggleDrum.textContent = "Refill Tank to OK";
      btnSimToggleDrum.setAttribute("data-level", "OK");
    } else {
      btnSimToggleDrum.textContent = "Toggle Tank to LOW";
      btnSimToggleDrum.setAttribute("data-level", "LOW");
    }
  }

  const bpDrumBadge = document.getElementById("bpDrumBadge");
  const bpDrumLevelText = document.getElementById("bpDrumLevelText");
  if (bpDrumBadge) {
    bpDrumBadge.textContent = isDrumLow ? "LOW WATER" : "NORMAL";
    bpDrumBadge.className = isDrumLow ? "status-pill pill-warning" : "status-pill pill-optimal";
  }
  if (bpDrumLevelText) {
    bpDrumLevelText.textContent = isDrumLow ? "LOW (Float Triggered - Cutoff Active)" : "HIGH (Tank Adequate)";
  }

  // 4. Pump Status
  const pumpState = state.pump_state || (state.pump_running ? "RUNNING" : "IDLE");
  const bpPumpBadge = document.getElementById("bpPumpBadge");
  if (bpPumpBadge) {
    bpPumpBadge.textContent = pumpState;
    bpPumpBadge.className = pumpState === "RUNNING" ? "status-pill pill-active-pump" : "status-pill pill-idle";
  }

  // 5. Battery & RSSI
  if (state.battery_v !== undefined) {
    const battStr = `${Number(state.battery_v).toFixed(1)}V`;
    const simBatt = document.getElementById("simBatteryVal");
    if (simBatt) simBatt.textContent = battStr;
    const bpBatt = document.getElementById("bpBatteryVal");
    if (bpBatt) bpBatt.textContent = `${battStr} Li-ion`;
  }
  if (state.rssi_dbm !== undefined) {
    const bpRssi = document.getElementById("bpRssiVal");
    if (bpRssi) bpRssi.textContent = `${state.rssi_dbm} dBm`;
  }
}

// Periodic watchdog to re-evaluate hardware heartbeat freshness every 5s
setInterval(() => {
  if (window.__lastBalconyState) {
    updateBalconyState(window.__lastBalconyState);
  }
}, 5000);

