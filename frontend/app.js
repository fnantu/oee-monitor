/* ===== API BASE ===== */
const API = "http://" + location.hostname + ":8000";

/* ===== TAB NAV ===== */
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => {
      b.classList.remove("border-green-400", "text-green-400", "font-semibold");
      b.classList.add("border-transparent", "text-gray-400");
    });
    btn.classList.add("border-green-400", "text-green-400", "font-semibold");
    btn.classList.remove("border-transparent", "text-gray-400");
    document.querySelectorAll(".tab-content").forEach(tc => tc.classList.add("hidden"));
    document.getElementById("tab-" + btn.dataset.tab).classList.remove("hidden");
    if (btn.dataset.tab === "explore") setTimeout(loadExplore, 100);
    if (btn.dataset.tab === "reports") setTimeout(loadReports, 100);
  });
});

/* ===== FLATPICKR ===== */
const today = new Date().toISOString().slice(0,10);
document.querySelectorAll(".datepicker").forEach(el => {
  flatpickr(el, { dateFormat: "Y-m-d", defaultDate: today });
  el.value = today;
});

/* ===== CONSTS ===== */
const MACH_STYLES = {
  "M-01-Torna": { color: "#34d399", label: "Torna" },
  "M-02-Pres":  { color: "#60a5fa", label: "Pres" },
  "M-03-CNC":   { color: "#f472b6", label: "CNC" },
};
const METRIC_LABELS = {
  oee: "OEE", availability: "Kul.lık", performance: "Perf.",
  quality: "Kalite", temperature: "Sıcaklık", vibration: "Titreşim",
  pressure: "Basınç", produced_qty: "Üretim", defective_qty: "Kusur",
};

/* ===== ECHARTS HELPERS ===== */
function initECharts(id) {
  const el = document.getElementById(id);
  if (!el) { console.warn("ECharts: #" + id + " bulunamadı"); return null; }
  try {
    return echarts.init(el, null, { renderer: "svg" });
  } catch (e) {
    console.warn("ECharts init hatası (" + id + "):", e);
    return null;
  }
}
const ECHART_THEME = {
  axisLine: { lineStyle: { color: "#374151" } },
  splitLine: { lineStyle: { color: "#374151" } },
  axisLabel: { color: "#9ca3af", fontSize: 9 },
  legendText: { color: "#9ca3af", fontSize: 9 },
  titleText: { color: "#d1d5db", fontSize: 11 },
};

/* ===== LIVE TAB ===== */
const MAX_P = 60;
const liveLabels = [];
const liveOeeData = { "M-01-Torna": [], "M-02-Pres": [], "M-03-CNC": [] };
const liveTempData = { "M-01-Torna": [], "M-02-Pres": [], "M-03-CNC": [] };

const liveOeeChart = initECharts("oeeChart");
if (liveOeeChart) {
  liveOeeChart.setOption({
    grid: { left: 35, right: 10, top: 5, bottom: 5 },
    xAxis: { type: "category", show: false },
    yAxis: { type: "value", min: 0, max: 100, ...ECHART_THEME, axisLabel: { ...ECHART_THEME.axisLabel, formatter: "{value}%" } },
    tooltip: { trigger: "axis", formatter: p => p.map(s => s.seriesName + ": " + s.value + "%").join("<br/>") },
    legend: { textStyle: ECHART_THEME.legendText },
    series: Object.entries(MACH_STYLES).map(([id, m]) => ({ name: m.label, type: "line", data: [], smooth: true, lineStyle: { color: m.color, width: 2 }, showSymbol: false, emphasis: { focus: "series" } })),
  });
}

const liveTempChart = initECharts("tempChart");
if (liveTempChart) {
  liveTempChart.setOption({
    grid: { left: 35, right: 10, top: 5, bottom: 5 },
    xAxis: { type: "category", show: false },
    yAxis: { type: "value", ...ECHART_THEME, axisLabel: { ...ECHART_THEME.axisLabel, formatter: "{value}°C" } },
    tooltip: { trigger: "axis" },
    legend: { textStyle: ECHART_THEME.legendText },
  series: Object.entries(MACH_STYLES).map(([id, m]) => ({ name: m.label, type: "line", data: [], smooth: true, lineStyle: { color: m.color, width: 2 }, showSymbol: false })),
  });
}

const gridEl = document.getElementById("machineGrid");
Object.keys(MACH_STYLES).forEach(mid => {
  const m = MACH_STYLES[mid];
  const card = document.createElement("div");
  card.id = "card-" + mid;
  card.className = "bg-gray-800 rounded p-3 border border-gray-700";
  card.innerHTML = `<div class="flex justify-between items-start mb-1"><span class="text-sm font-semibold">${m.label}</span><span class="text-xs text-gray-500">${mid}</span></div>
    <div class="grid grid-cols-3 gap-1 text-center mb-1">
      <div><div class="text-lg font-bold" id="oee-${mid}">--</div><div class="text-xs text-gray-400">OEE</div></div>
      <div><div class="text-lg font-bold" id="temp-${mid}">--</div><div class="text-xs text-gray-400">Sıcak</div></div>
      <div><div class="text-lg font-bold" id="prod-${mid}">--</div><div class="text-xs text-gray-400">Üretim</div></div>
    </div>
    <div class="flex justify-between text-xs"><span class="text-gray-400">T:<span id="vib-${mid}">--</span> B:<span id="pres-${mid}">--</span></span><span id="status-${mid}" class="px-1.5 py-0.5 rounded font-bold text-xs">--</span></div>`;
  gridEl.appendChild(card);
});

let liveIdx = 0;
function updateLive(data) {
  const m = MACH_STYLES[data.machine_id];
  if (!m) return;
  document.getElementById("oee-" + data.machine_id).textContent = data.oee.toFixed(1) + "%";
  document.getElementById("temp-" + data.machine_id).textContent = data.temperature.toFixed(1) + "°C";
  document.getElementById("prod-" + data.machine_id).textContent = data.produced_qty + (data.defective_qty > 0 ? "/" + data.defective_qty : "");
  document.getElementById("vib-" + data.machine_id).textContent = data.vibration.toFixed(2);
  document.getElementById("pres-" + data.machine_id).textContent = data.pressure.toFixed(1);
  const se = document.getElementById("status-" + data.machine_id);
  se.textContent = data.status;
  const cls = { RUNNING: "bg-green-900 text-green-300", IDLE: "bg-yellow-900 text-yellow-300", ERROR: "bg-red-900 text-red-300", DOWN: "bg-gray-700 text-gray-300" };
  se.className = "px-1.5 py-0.5 rounded font-bold text-xs " + (cls[data.status] || cls.DOWN);

  liveIdx++;
  liveLabels.push(data.time ? data.time.slice(11, 19) : "" + liveIdx);
  liveOeeData[data.machine_id].push(data.oee);
  liveTempData[data.machine_id].push(data.temperature);
  if (liveLabels.length > MAX_P) {
    liveLabels.shift();
    Object.values(liveOeeData).forEach(a => a.shift());
    Object.values(liveTempData).forEach(a => a.shift());
  }
  if (liveOeeChart) liveOeeChart.setOption({ xAxis: { data: [...liveLabels] }, series: Object.entries(MACH_STYLES).map(([id, m]) => ({ data: [...liveOeeData[id]] })) });
  if (liveTempChart) liveTempChart.setOption({ xAxis: { data: [...liveLabels] }, series: Object.entries(MACH_STYLES).map(([id, m]) => ({ data: [...liveTempData[id]] })) });
}

/* ===== WS ===== */
function connectWS() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.hostname + ":8000/ws");
  ws.onopen = () => {
    document.getElementById("wsIndicator").className = "w-2 h-2 rounded-full bg-green-400 animate-pulse";
    document.getElementById("wsStatus").textContent = "Bağlı";
  };
  ws.onmessage = e => updateLive(JSON.parse(e.data));
  ws.onclose = () => {
    document.getElementById("wsIndicator").className = "w-2 h-2 rounded-full bg-red-500";
    document.getElementById("wsStatus").textContent = "Koptu, yeniden...";
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => ws.close();
}
connectWS();

/* ===== GLOBAL RESIZE ===== */
let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    [liveOeeChart, liveTempChart, expChart, rptOeeChart, rptPieChart, rptProdChart].forEach(c => {
      if (c && typeof c.resize === "function") c.resize();
    });
  }, 200);
});

/* ===== EXPLORE TOGGLES ===== */
const expFilterToggle = document.getElementById("expFilterToggle");
const expFilterPanel = document.getElementById("expFilterPanel");
const expFilterIcon = document.getElementById("expFilterIcon");
if (expFilterToggle) {
  expFilterToggle.addEventListener("click", () => {
    const hidden = expFilterPanel.classList.toggle("hidden");
    expFilterIcon.textContent = hidden ? "▶" : "▼";
    if (expChart) setTimeout(() => expChart.resize(), 50);
  });
}
const expFullBtn = document.getElementById("expFullscreenBtn");
const expContainer = document.getElementById("expChartContainer");
if (expFullBtn) {
  expFullBtn.addEventListener("click", () => {
    const isFs = expContainer.classList.toggle("fullscreen");
    expFullBtn.textContent = isFs ? "✕" : "⛶";
    if (expChart) setTimeout(() => expChart.resize(), 100);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && expContainer.classList.contains("fullscreen")) {
      expContainer.classList.remove("fullscreen");
      expFullBtn.textContent = "⛶";
      if (expChart) setTimeout(() => expChart.resize(), 100);
    }
  });
}
const expTableToggle = document.getElementById("expTableToggle");
const expTableWrap = document.getElementById("expTableWrap");
const expTableIcon = document.getElementById("expTableIcon");
if (expTableToggle) {
  expTableToggle.addEventListener("click", () => {
    const hidden = expTableWrap.classList.toggle("hidden");
    expTableIcon.textContent = hidden ? "▶" : "▼";
    if (expChart) setTimeout(() => expChart.resize(), 50);
  });
}

/* ===== EXPLORE TAB ===== */
let expChart = null;

function parseTimeseriesCol(key) {
  for (const mid of Object.keys(MACH_STYLES)) {
    const prefix = mid + "_";
    if (key.startsWith(prefix)) {
      const suffix = key.slice(prefix.length);
      const us = suffix.lastIndexOf("_");
      if (us < 0) return null;
      return { machine_id: mid, metric: suffix.slice(0, us), agg: suffix.slice(us + 1) };
    }
  }
  return null;
}

function getExplDateRange() {
  const active = document.querySelector("#expPresets .active");
  const range = active ? active.dataset.range : "1h";
  const now = new Date();
  let from = new Date(now), to = new Date(now);
  if (range === "1h") from.setHours(now.getHours() - 1);
  else if (range === "6h") from.setHours(now.getHours() - 6);
  else if (range === "24h") from.setDate(now.getDate() - 1);
  else if (range === "today") { from.setHours(0,0,0,0); }
  else if (range === "7d") from.setDate(now.getDate() - 7);
  else if (range === "30d") from.setDate(now.getDate() - 30);
  const customFrom = document.getElementById("expFrom").value;
  const customTo = document.getElementById("expTo").value;
  if (customFrom) from = new Date(customFrom);
  if (customTo) to = new Date(customTo);
  return { from: from.toISOString().slice(0,10), to: to.toISOString().slice(0,10) };
}

document.querySelectorAll("#expPresets .preset-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#expPresets .preset-btn").forEach(b => {
      b.classList.remove("bg-green-800", "active");
      b.classList.add("bg-gray-700");
    });
    btn.classList.add("bg-green-800", "active");
    btn.classList.remove("bg-gray-700");
    if (btn.dataset.range !== "custom") {
      const d = getExplDateRange();
      document.getElementById("expFrom").value = d.from;
      document.getElementById("expTo").value = d.to;
    }
    loadExplore();
  });
});

document.getElementById("expLoadBtn").addEventListener("click", loadExplore);

async function loadExplore() {
  const mids = [...document.querySelectorAll(".exp-mach:checked")].map(el => el.value).join(",");
  if (!mids) return;
  const metrics = [...document.querySelectorAll(".exp-metric:checked")].map(el => el.value).join(",");
  if (!metrics) return;
  const gran = document.getElementById("expGranularity").value;
  const range = getExplDateRange();
  const url = `${API}/api/reports/timeseries?machine_ids=${mids}&metrics=${metrics}&granularity=${gran}&from=${range.from}&to=${range.to}`;
  const errEl = document.getElementById("expError");
  try {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}: ${await resp.text()}`);
    const data = await resp.json();
    errEl.classList.add("hidden");
    renderExploreChart(data, mids, metrics, document.getElementById("expChartType").value);
    renderExploreTable(data);
  } catch (e) {
    errEl.classList.remove("hidden");
    errEl.textContent = "Hata: " + e.message;
    console.error("Explore error:", e);
  }
}

function formatBucket(bucket, gran) {
  if (!bucket) return "";
  if (gran === "1d") return bucket.slice(0,10);
  if (gran === "1h" || gran === "4h") return bucket.slice(11,16);
  return bucket.slice(11,19);
}

function renderExploreChart(data, mids, metrics, chartType) {
  const gran = document.getElementById("expGranularity").value;
  const colorMap = { oee: "#34d399", availability: "#60a5fa", performance: "#f472b6", quality: "#fbbf24", temperature: "#fb923c", vibration: "#a78bfa", pressure: "#f87171", produced_qty: "#2dd4bf", defective_qty: "#ef4444" };
  if (!data.length) return;
  if (expChart) expChart.dispose();
  expChart = initECharts("expChart");
  const labels = data.map(r => formatBucket(r.bucket, gran));
  const series = [];
  const seen = {};
  Object.keys(data[0]).forEach(key => {
    if (key === "bucket") return;
    const info = parseTimeseriesCol(key);
    if (!info) return;
    const ml = METRIC_LABELS[info.metric] || info.metric;
    const mlbl = MACH_STYLES[info.machine_id]?.label || info.machine_id;
    const label = `${mlbl} - ${ml}`;
    if (seen[label]) return;
    seen[label] = true;
    series.push({
      name: label, type: chartType === "bar" ? "bar" : "line",
      data: data.map(r => r[key] || 0),
      smooth: true, showSymbol: false,
      lineStyle: { color: colorMap[info.metric] || "#fff", width: 2 },
      itemStyle: { color: colorMap[info.metric] || "#fff" },
      emphasis: { focus: "series" },
    });
  });
  expChart.setOption({
    grid: { left: 45, right: 15, top: 10, bottom: 20 },
    tooltip: { trigger: "axis" },
    legend: { textStyle: ECHART_THEME.legendText },
    xAxis: { type: "category", data: labels, axisLine: ECHART_THEME.axisLine, axisLabel: { ...ECHART_THEME.axisLabel, rotate: 45 } },
    yAxis: { type: "value", ...ECHART_THEME, axisLabel: { ...ECHART_THEME.axisLabel, formatter: "{value}" } },
    series,
  });
}

function renderExploreTable(data) {
  const gran = document.getElementById("expGranularity").value;
  if (!data.length) { document.getElementById("expTable").innerHTML = ""; return; }
  const cols = Object.keys(data[0]);
  let html = "<thead><tr class='text-gray-400'>" + cols.map(c => `<th class='text-left p-1'>${c}</th>`).join("") + "</tr></thead><tbody>";
  data.forEach(r => {
    html += "<tr class='border-t border-gray-700'>" + cols.map(c => `<td class='p-1'>${typeof r[c] === 'number' ? r[c].toFixed(2) : formatBucket(r[c], gran)}</td>`).join("") + "</tr>";
  });
  html += "</tbody>";
  document.getElementById("expTable").innerHTML = html;
}

/* ===== RAPORLAR TAB ===== */
let rptOeeChart = null, rptPieChart = null, rptProdChart = null;

function getRptDateRange() {
  const active = document.querySelector("#rptPresets .active") || document.querySelector("#rptPresets .rpt-preset");
  const range = active ? active.dataset.range : "today";
  const now = new Date();
  let from = new Date(now), to = new Date(now);
  if (range === "today") { from.setHours(0,0,0,0); }
  else if (range === "yesterday") { from.setDate(now.getDate() - 1); from.setHours(0,0,0,0); to.setDate(now.getDate() - 1); to.setHours(23,59,59,999); }
  else if (range === "7d") from.setDate(now.getDate() - 7);
  else if (range === "30d") from.setDate(now.getDate() - 30);
  const cf = document.getElementById("rptFrom").value;
  const ct = document.getElementById("rptTo").value;
  if (cf) from = new Date(cf);
  if (ct) to = new Date(ct);
  return { from: from.toISOString().slice(0,10), to: to.toISOString().slice(0,10) };
}

document.querySelectorAll("#rptPresets .rpt-preset").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#rptPresets .rpt-preset").forEach(b => {
      b.classList.remove("bg-green-800", "active");
      b.classList.add("bg-gray-700");
    });
    btn.classList.add("bg-green-800", "active");
    btn.classList.remove("bg-gray-700");
    const d = getRptDateRange();
    document.getElementById("rptFrom").value = d.from;
    document.getElementById("rptTo").value = d.to;
    loadReports();
  });
});

document.getElementById("rptLoadBtn").addEventListener("click", loadReports);

async function loadReports() {
  const mids = [...document.querySelectorAll(".rpt-mach:checked")].map(el => el.value);
  if (!mids.length) return;
  const range = getRptDateRange();
  const midsStr = mids.join(",");
  const errEl = document.getElementById("rptError");
  try {
    const res = await Promise.all([
      fetch(`${API}/api/reports/stats?machine_ids=${midsStr}&from=${range.from}&to=${range.to}`),
      fetch(`${API}/api/reports/timeseries?machine_ids=${midsStr}&metrics=oee&granularity=1h&from=${range.from}&to=${range.to}`),
      fetch(`${API}/api/reports/top-errors?machine_ids=${midsStr}&from=${range.from}&to=${range.to}&limit=10`),
    ]);
    for (const r of res) { if (!r.ok) throw new Error(`HTTP ${r.status} from ${r.url}`); }
    const [stats, ts, errors] = await Promise.all(res.map(r => r.json()));
    errEl.classList.add("hidden");
    renderRptCards(stats);
    renderRptOeeChart(ts, mids);
    renderRptPieChart(errors);
    renderRptProdChart(stats);
    renderRptErrors(errors);
  } catch (e) {
    errEl.classList.remove("hidden");
    errEl.textContent = "Hata: " + e.message;
    console.error("Reports error:", e);
  }
}

function renderRptCards(stats) {
  document.getElementById("rptCards").innerHTML = stats.map(s => {
    const m = MACH_STYLES[s.machine_id] || {};
    return `<div class="bg-gray-800 rounded p-3 border border-gray-700 text-xs">
      <div class="font-semibold text-sm mb-1" style="color:${m.color || '#fff'}">${m.label || s.machine_id}</div>
      <div class="grid grid-cols-2 gap-1">
        <span>OEE: <b>${s.avg_oee}%</b></span>
        <span>Max: <b class="text-green-400">${s.max_oee}%</b></span>
        <span>Min: <b class="text-red-400">${s.min_oee}%</b></span>
        <span>Uptime: <b>${s.uptime_pct}%</b></span>
        <span>Üretim: <b>${s.total_production}</b></span>
        <span>Kusur: <b class="text-red-400">${s.total_defective}</b></span>
        <span>Duruş: <b>${s.downtime_count} olay</b></span>
        <span>MTBF: <b>${s.mtbf_seconds !== null ? s.mtbf_seconds + 's' : '-'}</b></span>
      </div>
    </div>`;
  }).join("");
}

function renderRptOeeChart(data, mids) {
  if (rptOeeChart) rptOeeChart.dispose();
  if (!data || !data.length) return;
  rptOeeChart = initECharts("rptOeeChart");
  const labels = data.map(r => r.bucket ? r.bucket.slice(11,16) : "");
  const series = mids.map(mid => {
    const m = MACH_STYLES[mid];
    return { name: m?.label || mid, type: "line", data: data.map(r => r[mid + "_oee_avg"] || 0), smooth: true, showSymbol: false, lineStyle: { color: m?.color || "#fff", width: 2 }, emphasis: { focus: "series" } };
  });
  rptOeeChart.setOption({
    grid: { left: 40, right: 10, top: 30, bottom: 15 },
    tooltip: { trigger: "axis" },
    title: { text: "OEE Trendi", ...ECHART_THEME.titleText, left: "center" },
    legend: { textStyle: ECHART_THEME.legendText, top: 15 },
    xAxis: { type: "category", data: labels, axisLine: ECHART_THEME.axisLine, axisLabel: ECHART_THEME.axisLabel },
    yAxis: { type: "value", min: 0, max: 100, ...ECHART_THEME, axisLabel: { ...ECHART_THEME.axisLabel, formatter: "{value}%" } },
    series,
  });
}

function renderRptPieChart(errors) {
  if (rptPieChart) rptPieChart.dispose();
  const canvas = document.getElementById("rptPieChart");
  const parent = canvas.parentElement;
  if (!errors.length) {
    canvas.style.display = "none";
    let msg = parent.querySelector(".empty-msg");
    if (!msg) { msg = document.createElement("div"); msg.className = "empty-msg text-xs text-gray-400 text-center py-8"; parent.appendChild(msg); }
    msg.textContent = "Bu dönem için duruş kaydı yok";
    msg.style.display = "";
    return;
  }
  canvas.style.display = "";
  const msg = parent.querySelector(".empty-msg");
  if (msg) msg.style.display = "none";
  const colors = ["#ef4444","#f59e0b","#3b82f6","#8b5cf6","#10b981","#ec4899","#14b8a6","#f97316","#6366f1","#84cc16"];
  rptPieChart = initECharts("rptPieChart");
  rptPieChart.setOption({
    tooltip: { trigger: "item", formatter: "{b}: {c} olay ({d}%)" },
    title: { text: "Hata Dağılımı", ...ECHART_THEME.titleText, left: "center" },
    legend: { textStyle: ECHART_THEME.legendText, top: 25 },
    series: [{
      type: "pie", radius: ["40%", "70%"],
      data: errors.map((e, i) => ({ name: e.reason_code, value: e.event_count, itemStyle: { color: colors[i % colors.length] } })),
      label: { color: "#9ca3af", fontSize: 9 },
    }],
  });
}

function renderRptProdChart(stats) {
  if (rptProdChart) rptProdChart.dispose();
  rptProdChart = initECharts("rptProdChart");
  rptProdChart.setOption({
    grid: { left: 45, right: 10, top: 30, bottom: 15 },
    tooltip: { trigger: "axis" },
    title: { text: "Üretim Karşılaştırması", ...ECHART_THEME.titleText, left: "center" },
    legend: { textStyle: ECHART_THEME.legendText, top: 15 },
    xAxis: { type: "category", data: stats.map(s => MACH_STYLES[s.machine_id]?.label || s.machine_id), axisLine: ECHART_THEME.axisLine, axisLabel: ECHART_THEME.axisLabel },
    yAxis: { type: "value", ...ECHART_THEME, axisLabel: ECHART_THEME.axisLabel },
    series: [
      { name: "Üretim", type: "bar", data: stats.map(s => s.total_production), itemStyle: { color: "#34d399" } },
      { name: "Kusur", type: "bar", data: stats.map(s => s.total_defective), itemStyle: { color: "#ef4444" } },
    ],
  });
}

function renderRptErrors(errors) {
  const el = document.getElementById("rptTopErrors");
  if (!errors.length) { el.innerHTML = "<span class='text-gray-500'>Veri yok</span>"; return; }
  el.innerHTML = errors.map(e =>
    `<div class="flex justify-between border-b border-gray-700 py-1">
      <span class="text-red-400">${e.reason_code}</span>
      <span>${e.event_count} olay / ${e.total_seconds}s</span>
    </div>`
  ).join("");
}

/* ===== EXPORT TAB ===== */
document.getElementById("expDownloadBtn").addEventListener("click", () => {
  const fmt = document.querySelector('input[name="expFmt"]:checked').value;
  const mid = document.getElementById("expMachSel").value;
  const f = document.getElementById("expFromDate").value;
  const t = document.getElementById("expToDate").value;
  let url = `${API}/api/reports/export?format=${fmt}`;
  if (mid) url += `&machine_id=${mid}`;
  if (f) url += `&from=${f}`;
  if (t) url += `&to=${t}`;
  window.open(url, "_blank");
});

/* ===== INIT ===== */
document.querySelectorAll(".datepicker").forEach(el => {
  el.value = today;
  try { el._flatpickr.setDate(today); } catch(e) {}
});
document.getElementById("expFrom").value = today;
document.getElementById("expTo").value = today;
document.getElementById("rptFrom").value = today;
document.getElementById("rptTo").value = today;
document.getElementById("expFromDate").value = today;
document.getElementById("expToDate").value = today;
