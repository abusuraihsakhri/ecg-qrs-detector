"use strict";

const el = (id) => document.getElementById(id);
const fileInput = el("ecg-file");
const fsInput = el("sampling-rate");
const refractoryInput = el("refractory");
const runButton = el("run-file");
const demoButton = el("run-demo");
const exportButton = el("export-peaks");
const statusEl = el("status");
const errorEl = el("error");
const summaryEl = el("summary");
const canvas = el("ecg-plot");
let python = null;
let lastAnalysis = null;
let isBusy = false;

function status(message) {
  statusEl.textContent = message;
}
function error(message) {
  errorEl.textContent = message || "";
  errorEl.hidden = !message;
}
function setBusy(value) {
  isBusy = value;
  runButton.disabled = value || !python;
  demoButton.disabled = value || !python;
  exportButton.disabled = value || !lastAnalysis || !lastAnalysis.peaks.length;
}
function formatted(value, digits = 1) {
  return value === null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}

async function bootstrap() {
  status("Loading the Python ECG engine (first load may take a moment)…");
  try {
    if (typeof loadPyodide !== "function") {
      throw new Error("Pyodide could not load. Check network access or content blockers.");
    }
    const response = await fetch("./qrs_detector.py");
    if (!response.ok) {
      throw new Error("ECG detector source is missing from the deployed application.");
    }
    const source = await response.text();
    python = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/" });
    python.FS.writeFile("/tmp/qrs_detector.py", source, { encoding: "utf8" });
    python.FS.writeFile("/tmp/analysis.py", await fetchBridge(), { encoding: "utf8" });
    python.runPython("import sys; sys.path.insert(0, '/tmp'); import analysis");
    status("Ready. Processing runs locally in your browser.");
    setBusy(false);
  } catch (exc) {
    python = null;
    status("Unable to load the local Python engine.");
    error(String(exc && exc.message ? exc.message : exc));
    setBusy(false);
  }
}

async function fetchBridge() {
  const response = await fetch("./analysis.py");
  if (!response.ok) {
    throw new Error("Browser analysis module is missing from the deployment.");
  }
  return response.text();
}

async function process(run) {
  if (isBusy || !python) return;
  setBusy(true);
  error("");
  status("Analyzing ECG with the Python QRS detector…");
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  try {
    const output = await run();
    const data = JSON.parse(output);
    lastAnalysis = data;
    showAnalysis(data);
    status("Analysis completed locally. No ECG samples were uploaded.");
  } catch (exc) {
    lastAnalysis = null;
    summaryEl.hidden = true;
    status("Analysis failed.");
    error(String(exc && exc.message ? exc.message : exc));
  } finally {
    setBusy(false);
  }
}

runButton.addEventListener("click", () => process(async () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) throw new Error("Select an ECG CSV file.");
  if (file.size > 3000000) throw new Error("CSV exceeds the 3 MB browser limit.");
  const fsText = fsInput.value.trim();
  const fs = fsText === "" ? null : Number(fsText);
  const refractory = Number(refractoryInput.value);
  if (fs !== null && (!Number.isFinite(fs) || fs <= 0)) {
    throw new Error("Sampling rate must be a positive number.");
  }
  if (!Number.isFinite(refractory) || refractory < 0 || refractory > 2) {
    throw new Error("Refractory period must be between 0 and 2 seconds.");
  }
  python.globals.set("input_csv_text", await file.text());
  python.globals.set("requested_fs", fs);
  python.globals.set("requested_refractory", refractory);
  return python.runPython("analysis.analyze_csv(input_csv_text, requested_fs, requested_refractory)");
}));

demoButton.addEventListener("click", () => process(async () => {
  return python.runPython("analysis.analyze_demo(12, 250, 72)");
}));

exportButton.addEventListener("click", () => {
  if (!lastAnalysis) return;
  const data = lastAnalysis;
  const headers = "r_peak_index,r_peak_time_sec,rr_interval_ms,instantaneous_hr_bpm";
  const rows = data.peaks.map((peak, index) => [
    peak, (peak / data.fs).toFixed(4),
    index ? data.metrics.rr_intervals_ms[index - 1].toFixed(2) : "",
    index ? data.metrics.instantaneous_hr_bpm[index - 1].toFixed(2) : ""
  ].join(","));
  const blob = new Blob([[headers, ...rows].join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "ecg_r_peaks.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function showAnalysis(data) {
  el("beat-count").textContent = String(data.metrics.n_beats);
  el("mean-hr").textContent = formatted(data.metrics.mean_hr_bpm) + " bpm";
  el("sdnn").textContent = formatted(data.metrics.sdnn_ms) + " ms";
  el("rmssd").textContent = formatted(data.metrics.rmssd_ms) + " ms";
  el("pnn50").textContent = formatted(data.metrics.pnn50_pct) + " %";
  el("rhythm").textContent = data.rhythm.rhythm.replaceAll("_", " ");
  el("file-info").textContent = data.sample_count.toLocaleString() + " samples · " +
    formatted(data.fs, 2) + " Hz · " + formatted(data.duration_sec, 2) + " s";
  summaryEl.hidden = false;
  drawPlot(data);
}

function drawPlot(data) {
  const rect = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  const width = Math.max(300, Math.round(rect.width));
  const height = 300;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#0d182a";
  ctx.fillRect(0, 0, width, height);
  const margin = { top: 20, bottom: 37, left: 46, right: 16 };
  const pw = width - margin.left - margin.right;
  const ph = height - margin.top - margin.bottom;
  const pts = data.plot;
  if (!pts.length) return;
  const vals = pts.map((point) => point[1]);
  let low = Math.min(...vals);
  let high = Math.max(...vals);
  if (low === high) { low -= 1; high += 1; }
  const pad = (high - low) * 0.08;
  low -= pad; high += pad;
  const maxTime = data.duration_sec;
  const x = (t) => margin.left + t / maxTime * pw;
  const y = (v) => margin.top + (high - v) / (high - low) * ph;
  ctx.strokeStyle = "#27364c";
  ctx.fillStyle = "#afbdd2";
  ctx.lineWidth = 1;
  ctx.font = "12px system-ui, sans-serif";
  for (let i = 0; i <= 4; i++) {
    const yy = margin.top + (ph / 4) * i;
    ctx.beginPath(); ctx.moveTo(margin.left, yy); ctx.lineTo(width - margin.right, yy); ctx.stroke();
    ctx.fillText((high - i * (high - low) / 4).toFixed(2), 5, yy + 4);
  }
  for (let i = 0; i <= 4; i++) {
    const time = maxTime * i / 4;
    ctx.fillText(time.toFixed(1) + "s", x(time) - 12, height - 14);
  }
  ctx.strokeStyle = "#64c6ff";
  ctx.lineWidth = 1.4;
  ctx.beginPath();
  pts.forEach((pt, i) => { if (i) ctx.lineTo(x(pt[0]), y(pt[1])); else ctx.moveTo(x(pt[0]), y(pt[1])); });
  ctx.stroke();
  ctx.fillStyle = "#fbac68";
  for (const point of data.peak_points) {
    ctx.beginPath(); ctx.arc(x(point[0]), y(point[1]), 3.7, 0, Math.PI * 2); ctx.fill();
  }
}

window.addEventListener("resize", () => {
  if (lastAnalysis && !summaryEl.hidden) drawPlot(lastAnalysis);
});
bootstrap();
