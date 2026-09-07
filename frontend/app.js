const API = "";  // same origin
const state = {
  latestPowerByMeter: new Map(),   // meter_id -> kW, for the live total
  chart: null,
  chartLabels: [],
  chartData: [],
};

function fmt(n, d = 1) {
  return n === null || n === undefined ? "–" : Number(n).toFixed(d);
}

async function loadSummary() {
  const r = await fetch(`${API}/api/dashboard/summary?hours=24`);
  const s = await r.json();
  document.getElementById("kpi-kwh").textContent = fmt(s.total_kwh, 0);
  document.getElementById("kpi-cost").textContent = fmt(s.total_cost_usd, 0);
  document.getElementById("kpi-co2").textContent = fmt(s.total_co2_kg, 0);
  document.getElementById("kpi-peak").textContent = fmt(s.peak_demand_kw, 1);
}

async function loadLeaderboard() {
  const r = await fetch(`${API}/api/dashboard/leaderboard?hours=24`);
  const rows = await r.json();
  const el = document.getElementById("leaderboard");
  if (!rows.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
  el.innerHTML = rows.map((row, i) => {
    const cls = row.performance_pct <= 0 ? "good" : "bad";
    const sign = row.performance_pct > 0 ? "+" : "";
    return `<div class="building-row">
      <span class="rank">${i + 1}</span>
      <span>${row.building_name}</span>
      <span class="pct ${cls}">${sign}${fmt(row.performance_pct, 0)}%</span>
    </div>`;
  }).join("");
}

async function loadHeatmap() {
  const r = await fetch(`${API}/api/dashboard/heatmap`);
  const cells = await r.json();
  const el = document.getElementById("heatmap");
  if (!cells.length) { el.innerHTML = '<p class="empty">No data yet.</p>'; return; }
  el.innerHTML = cells.map(c => `
    <div class="heat-cell ${c.status}">
      <div class="name">${c.building_name}</div>
      <div class="val">${fmt(c.intensity_kw_per_m2, 3)} kW/m²</div>
    </div>`).join("");
}

function initChart() {
  const ctx = document.getElementById("chart-canvas");
  state.chart = new Chart(ctx, {
    type: "line",
    data: {
      labels: state.chartLabels,
      datasets: [{
        label: "Campus load (kW)",
        data: state.chartData,
        borderColor: "#6FCF97",
        backgroundColor: "rgba(111,207,151,0.12)",
        fill: true,
        tension: 0.3,
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { ticks: { color: "#93AC9B", maxTicksLimit: 8 }, grid: { color: "#2A4A34" } },
        y: { ticks: { color: "#93AC9B" }, grid: { color: "#2A4A34" }, beginAtZero: true },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function pushChartPoint(ts, totalKw) {
  state.chartLabels.push(new Date(ts).toLocaleTimeString());
  state.chartData.push(Math.round(totalKw * 10) / 10);
  if (state.chartLabels.length > 120) { state.chartLabels.shift(); state.chartData.shift(); }
  state.chart.update("none");
}

function addAlert(a) {
  const el = document.getElementById("alerts");
  if (el.querySelector(".empty")) el.innerHTML = "";
  const item = document.createElement("div");
  item.className = `alert-item sev-${a.severity}`;
  item.innerHTML = `
    <div class="meta"><span>${a.severity.toUpperCase()} · ${a.kind}</span><span>${a.building}</span></div>
    <div class="msg">${a.message}</div>
    <div class="action">→ ${a.recommendation}</div>`;
  el.prepend(item);
  while (el.children.length > 25) el.removeChild(el.lastChild);
}

let lastChartPush = 0;
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/dashboard/ws/live`);

  ws.onopen = () => {
    document.getElementById("conn-dot").classList.remove("off");
    document.getElementById("conn-text").textContent = "live";
  };
  ws.onclose = () => {
    document.getElementById("conn-dot").classList.add("off");
    document.getElementById("conn-text").textContent = "reconnecting…";
    setTimeout(connectWS, 3000);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "reading") {
      state.latestPowerByMeter.set(msg.meter_id, msg.power_kw);
      const now = Date.now();
      if (now - lastChartPush > 2000) {
        lastChartPush = now;
        const total = [...state.latestPowerByMeter.values()].reduce((a, b) => a + b, 0);
        pushChartPoint(msg.ts, total);
      }
    } else if (msg.type === "alert") {
      addAlert(msg);
    }
  };
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadLeaderboard(), loadHeatmap()]);
}

initChart();
connectWS();
refreshAll();
setInterval(refreshAll, 15000);
