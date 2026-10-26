/* US Stock Screener — frontend logic */

const $ = (id) => document.getElementById(id);

const state = {
  results: [],
  sortBy: "score",
  sortDir: "desc",
  scanning: false,
  autoRefreshTimer: null,
  progressTimer: null,
};

const FIELDS = [
  "universe_size", "price_min", "price_max",
  "pe_min", "pe_max",
  "vol_ratio_min",
  "rsi_min", "rsi_max",
];

const PRESETS = {
  default:  { universe_size: 500, price_min: 5, price_max: 100, pe_min: 0, pe_max: 20, vol_ratio_min: 2,   rsi_min: 50, rsi_max: 100 },
  value:    { universe_size: 500, price_min: 5, price_max: 100, pe_min: 0, pe_max: 15, vol_ratio_min: 1,   rsi_min: 30, rsi_max: 70  },
  momentum: { universe_size: 500, price_min: 5, price_max: 100, pe_min: 0, pe_max: 40, vol_ratio_min: 1.5, rsi_min: 60, rsi_max: 100 },
  breakout: { universe_size: 500, price_min: 5, price_max: 100, pe_min: 0, pe_max: 30, vol_ratio_min: 3,   rsi_min: 50, rsi_max: 100 },
};

const RANGES = [
  ["price_min", "price_max", "Price min must be less than price max."],
  ["pe_min", "pe_max", "P/E min must be less than P/E max."],
  ["rsi_min", "rsi_max", "RSI min must be less than RSI max."],
];

const STORAGE_KEY = "screener.filters.v1";

const runBtn = $("run-btn");
const exportBtn = $("export-btn");
const autoRefreshCb = $("auto-refresh");
const useYesterdayCb = $("use_yesterday");
const statusEl = $("status");
const statusText = $("status-text");
const tbody = $("results-tbody");
const resultsMeta = $("results-meta");
const volLabelDay = $("vol-label-day");
const volHint = $("vol-hint");
const formError = $("form-error");
const progress = $("progress");
const progressText = $("progress-text");
const progressTimer = $("progress-timer");
const toast = $("toast");
const presetChips = document.querySelectorAll("[data-preset]");

/* ---------- Small helpers ---------- */
function setStatus(kind, text) {
  statusEl.classList.remove("busy", "error");
  if (kind === "busy") statusEl.classList.add("busy");
  if (kind === "error") statusEl.classList.add("error");
  statusText.textContent = text;
}

let toastTimer = null;
function showToast(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle("is-error", isError);
  toast.classList.add("is-shown");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-shown"), 4200);
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function escapeHTML(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- Persistence ---------- */
function saveFilters() {
  try {
    const data = { use_yesterday: useYesterdayCb.checked };
    FIELDS.forEach((f) => { data[f] = $(f).value; });
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch (_) { /* storage unavailable — ignore */ }
}

function loadFilters() {
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!data) return;
    FIELDS.forEach((f) => { if (data[f] !== undefined && data[f] !== "") $(f).value = data[f]; });
  } catch (_) { /* ignore */ }
}

/* ---------- Presets ---------- */
function syncPresetChips() {
  let match = null;
  for (const [name, values] of Object.entries(PRESETS)) {
    if (FIELDS.every((f) => parseFloat($(f).value) === values[f])) { match = name; break; }
  }
  presetChips.forEach((c) => c.classList.toggle("is-active", c.dataset.preset === match));
}

function applyPreset(name) {
  const values = PRESETS[name];
  if (!values) return;
  FIELDS.forEach((f) => { $(f).value = values[f]; });
  validate();
  syncPresetChips();
  saveFilters();
}

/* ---------- Validation ---------- */
function validate() {
  let message = "";
  document.querySelectorAll(".field.is-invalid").forEach((el) => el.classList.remove("is-invalid"));

  FIELDS.forEach((f) => {
    if ($(f).value.trim() === "" || Number.isNaN(parseFloat($(f).value))) {
      $(f).closest(".field").classList.add("is-invalid");
      message = message || "Every filter needs a number.";
    }
  });

  RANGES.forEach(([lo, hi, msg]) => {
    if (parseFloat($(lo).value) >= parseFloat($(hi).value)) {
      $(lo).closest(".field").classList.add("is-invalid");
      $(hi).closest(".field").classList.add("is-invalid");
      message = message || msg;
    }
  });

  formError.textContent = message;
  formError.hidden = !message;
  return !message;
}

/* ---------- Rendering ---------- */
function sparklineSVG(values) {
  if (!values || values.length < 2) return "";
  const w = 96, h = 26, pad = 2;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = (w - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) => [pad + i * step, h - pad - ((v - min) / range) * (h - pad * 2)]);
  const lineD = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaD =
    `M${pts[0][0].toFixed(1)},${h} ` +
    pts.map((p) => `L${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ") +
    ` L${pts[pts.length - 1][0].toFixed(1)},${h} Z`;
  const trend = values[values.length - 1] >= values[0] ? "up" : "down";
  return `<svg class="spark ${trend}" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
    <path class="spark-area" d="${areaD}"/>
    <path d="${lineD}"/>
  </svg>`;
}

function barCell(value, max, kind = "score") {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const fillClass = kind === "rsi" ? "bar-fill rsi" : "bar-fill";
  return `
    <div class="bar-cell">
      <div class="bar-track"><div class="${fillClass}" style="width:${pct.toFixed(1)}%"></div></div>
      <span class="bar-value mono">${fmt(value, 1)}</span>
    </div>`;
}

function renderSkeleton(rows = 8) {
  const row = `
    <tr class="skeleton">
      <td class="num"><span class="sk sk--sm"></span></td>
      <td><span class="sk sk--lg"></span></td>
      <td class="num"><span class="sk sk--md"></span></td>
      <td class="num"><span class="sk sk--md"></span></td>
      <td class="num"><span class="sk sk--sm"></span></td>
      <td class="num"><span class="sk sk--sm"></span></td>
      <td><span class="sk sk--lg"></span></td>
      <td><span class="sk sk--lg"></span></td>
      <td class="num"><span class="sk sk--lg"></span></td>
    </tr>`;
  tbody.innerHTML = row.repeat(rows);
}

function renderEmpty(title, sub) {
  tbody.innerHTML = `
    <tr class="empty"><td colspan="9">
      <div class="empty__inner">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 16l5-5 3.5 3.5L20 7"/></svg>
        <strong>${title}</strong>
        <span>${sub}</span>
      </div>
    </td></tr>`;
}

function updateSortHeaders() {
  document.querySelectorAll("thead th").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    th.removeAttribute("aria-sort");
    if (th.dataset.sort === state.sortBy) {
      th.classList.add(state.sortDir === "asc" ? "sort-asc" : "sort-desc");
      th.setAttribute("aria-sort", state.sortDir === "asc" ? "ascending" : "descending");
    }
  });
}

function renderResults({ animate = false } = {}) {
  updateSortHeaders();

  if (!state.results.length) {
    renderEmpty("No matches", "No stocks passed every filter. Try loosening a range or picking a preset.");
    exportBtn.disabled = true;
    resultsMeta.textContent = "";
    return;
  }

  const dir = state.sortDir === "asc" ? 1 : -1;
  const key = state.sortBy;
  const sorted = [...state.results].sort((a, b) => {
    const av = a[key], bv = b[key];
    if (typeof av === "string") return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });

  tbody.innerHTML = sorted.map((r, i) => {
    const up = r.change_pct >= 0;
    const ticker = escapeHTML(r.ticker);
    const yahooLink = `https://finance.yahoo.com/quote/${encodeURIComponent(r.ticker)}`;
    const anim = animate ? ` class="row-in" style="--i:${Math.min(i, 30)}"` : "";
    return `
      <tr${anim}>
        <td class="num rank">${i + 1}</td>
        <td class="ticker"><a href="${yahooLink}" target="_blank" rel="noopener">${ticker}</a></td>
        <td class="num mono cell-price">$${fmt(r.price, 2)}</td>
        <td class="num cell-chg"><span class="chg ${up ? "chg-up" : "chg-down"}">${up ? "+" : ""}${fmt(r.change_pct, 2)}%</span></td>
        <td class="num mono" data-label="P/E">${fmt(r.pe_ratio, 2)}</td>
        <td class="num mono" data-label="Vol×">${fmt(r.volume_ratio, 2)}×</td>
        <td data-label="RSI">${barCell(r.rsi, 100, "rsi")}</td>
        <td data-label="Score">${barCell(r.score, 100, "score")}</td>
        <td class="num cell-spark">${sparklineSVG(r.sparkline)}</td>
      </tr>`;
  }).join("");

  exportBtn.disabled = false;
  const label = document.querySelector(`th[data-sort="${state.sortBy}"]`)?.textContent.trim() || state.sortBy;
  resultsMeta.textContent = `${sorted.length} ${sorted.length === 1 ? "stock" : "stocks"} · sorted by ${label} ${state.sortDir === "asc" ? "↑" : "↓"}`;
}

function countUp(el, target) {
  if (typeof target !== "number") { el.textContent = target ?? "—"; return; }
  const start = performance.now();
  const dur = 700;
  const step = (t) => {
    const p = Math.min((t - start) / dur, 1);
    const eased = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(target * eased).toLocaleString("en-US");
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function pop(el) {
  el.classList.remove("pop");
  void el.offsetWidth;
  el.classList.add("pop");
}

function renderStats(stats, elapsed) {
  const map = {
    "stat-universe": stats.universe,
    "stat-with-data": stats.with_data,
    "stat-band": stats.in_price_band,
    "stat-passing": stats.passing,
  };
  Object.entries(map).forEach(([id, v]) => { countUp($(id), v); pop($(id)); });
  $("stat-runtime").textContent = elapsed != null ? `${elapsed}s` : "—";
  $("stat-time").textContent = new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
  pop($("stat-runtime"));
  pop($("stat-time"));
}

/* ---------- Scan ---------- */
const PROGRESS_STEPS = [
  [0, "Loading the stock universe…"],
  [3, "Fetching 60 days of prices…"],
  [15, "Fetching P/E ratios for the price band…"],
  [45, "Still working — large universes take a few minutes on a cold cache…"],
];

function startProgress() {
  progress.hidden = false;
  const t0 = Date.now();
  const tick = () => {
    const s = Math.floor((Date.now() - t0) / 1000);
    progressTimer.textContent = s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
    const step = [...PROGRESS_STEPS].reverse().find(([at]) => s >= at);
    progressText.textContent = step[1];
  };
  tick();
  state.progressTimer = setInterval(tick, 1000);
}

function stopProgress() {
  clearInterval(state.progressTimer);
  state.progressTimer = null;
  progress.hidden = true;
}

async function runScan() {
  if (state.scanning) return;
  if (!validate()) { showToast(formError.textContent, true); return; }

  state.scanning = true;
  runBtn.disabled = true;
  runBtn.classList.add("is-loading");
  runBtn.querySelector(".btn__label").textContent = "Scanning";
  setStatus("busy", "Scanning");
  startProgress();
  if (!state.results.length) renderSkeleton();
  saveFilters();

  const body = {};
  FIELDS.forEach((f) => {
    const el = $(f);
    body[f] = (f === "universe_size") ? parseInt(el.value, 10) : parseFloat(el.value);
  });
  body.use_yesterday = useYesterdayCb.checked;

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (resp.status === 429) {
      setStatus("error", "Busy");
      showToast("A scan is already running. Please wait for it to finish.", true);
      if (!state.results.length) renderEmpty("Scan in progress", "Another scan is running on the server. Try again in a moment.");
      return;
    }
    if (!resp.ok) {
      let detail = await resp.text();
      try { detail = JSON.parse(detail).detail || detail; } catch (_) { /* plain text */ }
      throw new Error(typeof detail === "string" ? detail : `HTTP ${resp.status}`);
    }

    const data = await resp.json();
    state.results = data.results || [];
    renderResults({ animate: true });
    renderStats(data.stats || {}, data.elapsed_s);
    setStatus("ok", `Ready · ${data.elapsed_s}s`);
  } catch (err) {
    console.error(err);
    setStatus("error", "Error");
    showToast(`Scan failed: ${err.message}`, true);
    if (!state.results.length) renderEmpty("Scan failed", "Something went wrong fetching data. Please try again.");
  } finally {
    state.scanning = false;
    runBtn.disabled = false;
    runBtn.classList.remove("is-loading");
    runBtn.querySelector(".btn__label").textContent = "Run screen";
    stopProgress();
  }
}

/* ---------- Export ---------- */
function exportCSV() {
  if (!state.results.length) return;
  const header = ["rank", "ticker", "price", "change_pct", "pe_ratio", "volume_ratio", "rsi", "score"];
  const lines = [header.join(",")];
  state.results.forEach((r, i) => {
    lines.push([i + 1, r.ticker, r.price, r.change_pct, r.pe_ratio, r.volume_ratio, r.rsi, r.score].join(","));
  });
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  a.href = url;
  a.download = `screener_${ts}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast(`Exported ${state.results.length} rows`);
}

/* ---------- Volume label ---------- */
function updateVolLabel() {
  const day = useYesterdayCb.checked ? "yesterday" : "today";
  volLabelDay.textContent = `(${day})`;
  volHint.textContent = `${day} ÷ 20-day avg`;
}

/* ---------- Events ---------- */
document.querySelectorAll("thead th.sortable").forEach((th) => {
  th.tabIndex = 0;
  const sort = () => {
    const key = th.dataset.sort;
    if (state.sortBy === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = key;
      state.sortDir = (key === "ticker" || key === "rank") ? "asc" : "desc";
    }
    if (state.results.length) renderResults(); else updateSortHeaders();
  };
  th.addEventListener("click", sort);
  th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); } });
});

FIELDS.forEach((f) => {
  $(f).addEventListener("input", () => {
    syncPresetChips();
    if (!formError.hidden) validate();
    saveFilters();
  });
  $(f).addEventListener("keydown", (e) => { if (e.key === "Enter") runScan(); });
});

presetChips.forEach((chip) => chip.addEventListener("click", () => applyPreset(chip.dataset.preset)));

autoRefreshCb.addEventListener("change", () => {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  if (autoRefreshCb.checked) {
    state.autoRefreshTimer = setInterval(() => { if (!state.scanning) runScan(); }, 5 * 60 * 1000);
    showToast("Auto-refresh on — rescanning every 5 minutes");
  }
});

useYesterdayCb.addEventListener("change", () => { updateVolLabel(); saveFilters(); });
runBtn.addEventListener("click", runScan);
exportBtn.addEventListener("click", exportCSV);

/* ---------- Init ---------- */
loadFilters();
syncPresetChips();
updateSortHeaders();

// During US market hours (9:30 AM – 4 PM ET, weekdays) today's bar is partial,
// so default to yesterday's complete bar.
(function autoDetectMarketHours() {
  const etStr = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).format(new Date());
  const m = etStr.match(/^(\w+),?\s+(\d+):(\d+)/);
  if (!m) return;
  const isWeekday = ["Mon", "Tue", "Wed", "Thu", "Fri"].includes(m[1]);
  const minutes = parseInt(m[2], 10) * 60 + parseInt(m[3], 10);
  if (isWeekday && minutes >= 9 * 60 + 30 && minutes < 16 * 60) {
    useYesterdayCb.checked = true;
    $("market-note").textContent = "· market open";
  }
  updateVolLabel();
})();
