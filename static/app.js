/* ============================================================
   Frontend logic for US Stock Screener
   ============================================================ */

const $ = (id) => document.getElementById(id);

const state = {
  results: [],
  sortBy: "score",
  sortDir: "desc",
  scanning: false,
  autoRefreshTimer: null,
};

// --- DOM refs ---
const runBtn = $("run-btn");
const exportBtn = $("export-btn");
const autoRefreshCb = $("auto-refresh");
const overlay = $("overlay");
const overlayText = $("overlay-text");
const overlaySub = $("overlay-sub");
const statusEl = $("status");
const statusText = $("status-text");
const tbody = $("results-tbody");
const resultsMeta = $("results-meta");

// --- Helpers ---
function setStatus(kind, text) {
  statusEl.classList.remove("busy", "error");
  if (kind === "busy") statusEl.classList.add("busy");
  if (kind === "error") statusEl.classList.add("error");
  statusText.textContent = text;
}

function showOverlay(text, sub) {
  overlayText.textContent = text || "Scanning…";
  overlaySub.textContent = sub || "This may take a few minutes for large universes";
  overlay.classList.remove("hidden");
}
function hideOverlay() {
  overlay.classList.add("hidden");
}

function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function sparklineSVG(values) {
  if (!values || values.length < 2) return "";
  const w = 90, h = 22, pad = 1;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = (w - pad * 2) / (values.length - 1);
  const pts = values.map((v, i) => {
    const x = pad + i * step;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return [x, y];
  });
  const lineD = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const areaD =
    `M${pts[0][0].toFixed(1)},${h - pad} ` +
    pts.map((p) => `L${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ") +
    ` L${pts[pts.length - 1][0].toFixed(1)},${h - pad} Z`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <path class="spark-area" d="${areaD}"/>
    <path d="${lineD}"/>
  </svg>`;
}

function barCell(value, max, kind = "score") {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const fillClass = kind === "rsi" ? "bar-fill rsi" : "bar-fill";
  return `
    <div class="bar-cell">
      <div class="bar-track">
        <div class="${fillClass}" style="width:${pct.toFixed(1)}%"></div>
      </div>
      <span class="bar-value mono">${fmt(value, 1)}</span>
    </div>`;
}

// --- Rendering ---
function renderResults() {
  if (!state.results.length) {
    tbody.innerHTML = `<tr class="empty"><td colspan="9">No stocks matched all criteria. Try loosening the filters.</td></tr>`;
    exportBtn.disabled = true;
    resultsMeta.textContent = "";
    return;
  }

  // Sort
  const dir = state.sortDir === "asc" ? 1 : -1;
  const key = state.sortBy;
  const sorted = [...state.results].sort((a, b) => {
    const av = a[key], bv = b[key];
    if (typeof av === "string") return av.localeCompare(bv) * dir;
    return (av - bv) * dir;
  });

  const rows = sorted.map((r, i) => {
    const chgClass = r.change_pct >= 0 ? "chg-up" : "chg-down";
    const chgSign = r.change_pct >= 0 ? "+" : "";
    const yahooLink = `https://finance.yahoo.com/quote/${encodeURIComponent(r.ticker)}`;
    return `
      <tr>
        <td class="num rank">${i + 1}</td>
        <td class="ticker"><a href="${yahooLink}" target="_blank" rel="noopener">${r.ticker}</a></td>
        <td class="num mono">$${fmt(r.price, 2)}</td>
        <td class="num mono ${chgClass}">${chgSign}${fmt(r.change_pct, 2)}%</td>
        <td class="num mono">${fmt(r.pe_ratio, 2)}</td>
        <td class="num mono">${fmt(r.volume_ratio, 2)}×</td>
        <td class="num">${barCell(r.rsi, 100, "rsi")}</td>
        <td class="num">${barCell(r.score, 100, "score")}</td>
        <td class="num">${sparklineSVG(r.sparkline)}</td>
      </tr>`;
  }).join("");

  tbody.innerHTML = rows;
  exportBtn.disabled = false;

  // Update sort indicator
  document.querySelectorAll("thead th").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === state.sortBy) {
      th.classList.add(state.sortDir === "asc" ? "sort-asc" : "sort-desc");
    }
  });

  resultsMeta.textContent = `${sorted.length} stocks · sorted by ${state.sortBy} ${state.sortDir}`;
}

function renderStats(stats, elapsed) {
  $("stat-universe").textContent = stats.universe ?? "—";
  $("stat-with-data").textContent = stats.with_data ?? "—";
  $("stat-band").textContent = stats.in_price_band ?? "—";
  $("stat-passing").textContent = stats.passing ?? "—";
  $("stat-runtime").textContent = elapsed != null ? `${elapsed}s` : "—";
  $("stat-time").textContent = new Date().toLocaleTimeString("en-US", { hour12: false });
}

// --- Scan ---
async function runScan() {
  if (state.scanning) return;
  state.scanning = true;
  runBtn.disabled = true;
  setStatus("busy", "Scanning");
  showOverlay("Scanning…", "Fetching prices, fundamentals, and computing indicators");

  const body = {
    universe_size: parseInt($("universe_size").value, 10),
    price_min: parseFloat($("price_min").value),
    price_max: parseFloat($("price_max").value),
    pe_max: parseFloat($("pe_max").value),
    vol_ratio_min: parseFloat($("vol_ratio_min").value),
    rsi_min: parseFloat($("rsi_min").value),
    rsi_max: parseFloat($("rsi_max").value),
  };

  try {
    const resp = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (resp.status === 429) {
      setStatus("error", "Scan in progress");
      hideOverlay();
      alert("A scan is already running. Please wait for it to finish.");
      return;
    }
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${txt}`);
    }

    const data = await resp.json();
    state.results = data.results || [];
    renderResults();
    renderStats(data.stats || {}, data.elapsed_s);
    setStatus("ok", `Ready · ${data.elapsed_s}s`);
  } catch (err) {
    console.error(err);
    setStatus("error", "Error");
    alert(`Scan failed: ${err.message}`);
  } finally {
    state.scanning = false;
    runBtn.disabled = false;
    hideOverlay();
  }
}

// --- CSV export ---
function exportCSV() {
  if (!state.results.length) return;
  const header = ["rank", "ticker", "price", "change_pct", "pe_ratio", "volume_ratio", "rsi", "score"];
  const lines = [header.join(",")];
  state.results.forEach((r, i) => {
    lines.push([
      i + 1, r.ticker, r.price, r.change_pct, r.pe_ratio,
      r.volume_ratio, r.rsi, r.score,
    ].join(","));
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
}

// --- Sorting ---
document.querySelectorAll("thead th.sortable").forEach((th) => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    if (state.sortBy === key) {
      state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    } else {
      state.sortBy = key;
      state.sortDir = (key === "ticker") ? "asc" : "desc";
    }
    renderResults();
  });
});

// --- Auto-refresh ---
autoRefreshCb.addEventListener("change", () => {
  if (state.autoRefreshTimer) {
    clearInterval(state.autoRefreshTimer);
    state.autoRefreshTimer = null;
  }
  if (autoRefreshCb.checked) {
    // 5 minutes
    state.autoRefreshTimer = setInterval(() => {
      if (!state.scanning) runScan();
    }, 5 * 60 * 1000);
  }
});

// --- Wire up ---
runBtn.addEventListener("click", runScan);
exportBtn.addEventListener("click", exportCSV);
