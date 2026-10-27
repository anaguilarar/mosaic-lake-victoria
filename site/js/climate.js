/* Climate layers (CHIRPS precipitation, CHIRTS-ERA5 temperature): yearly/seasonal stacks rendered
   to a MapLibre image source, a time bar (year slider + season + value/anomaly), and a click panel
   with the cell's monthly series against the 1991-2020 normal (one HTTP range request per cell). */

import { dataUrl } from "./config.js";
const APP = dataUrl("climate/app/");
const SCALE = 0.1, NODATA = -32768, MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

/* palettes — colour-blind-safe, deliberately distinct from the UI accent #1d5fbf */
const RAMPS = {
  precip: ["#fde737","#dec957","#bbad6c","#9b9376","#7c7b78","#61646f","#434e6b","#1a386f","#00224d"], // cividis reversed: dry -> wet
  temp: ["#060519","#2a115c","#5a157e","#872781","#b53679","#e14c66","#f97b5d","#feb179","#fce6a8"],   // magma: cool -> hot
  precip_anom: ["#543005","#8a5009","#bf812d","#dec07b","#f6e8c3","#f4f4f4","#c7eae5","#7ecbc0","#35978f","#00655d","#003c30"], // BrBG, centred 100 %
  temp_anom: ["#053061","#2064aa","#4393c3","#90c4dd","#d1e5f0","#f7f6f6","#fddbc7","#f3a380","#d6604d","#b0172a","#67001f"],   // RdBu, centred 0
};

export const VARS = {
  precip: { title: "Precipitation", vars: ["precip"], how: "total", units: "mm",
            source: "CHIRPS v3.0", anom: { units: "% of normal", centre: 100 } },
  temperature: { title: "Temperature", vars: ["tmean", "tmax", "tmin"], how: "mean", units: "°C",
                 source: "CHIRTS-ERA5", anom: { units: "°C vs normal", centre: 0 } },
  spi3: { title: "Drought index (SPI-3)", vars: ["spi3"], monthly: true, units: "SPI",
          source: "SPI-3 from CHIRPS v3.0" },
};
const SPI_CATS = [[-2, "extreme drought"], [-1.5, "severe drought"], [-1, "moderate drought"],
                  [1, "near normal"], [1.5, "moderately wet"], [2, "very wet"], [99, "extremely wet"]];
const spiCat = (v) => SPI_CATS.find(([t]) => v <= t)[1];
function spiMonths() {
  const n = state.meta.months_spi3.n, parts = state.meta.months_spi3.start.split("-").map(Number);
  return Array.from({ length: n }, (_, i) => {
    const t = (parts[0] * 12 + parts[1] - 1) + i;
    return Math.floor(t / 12) + "-" + String((t % 12) + 1).padStart(2, "0");
  });
}
const VAR_LABEL = { tmean: "Tmean (Tmax+Tmin)/2", tmax: "Tmax", tmin: "Tmin", precip: "Precipitation" };

const state = {
  meta: null, stacks: new Map(), normals: null, landmask: null,
  active: null,                     // "precip" | "temperature"
  v: "precip", season: "annual", mode: "value", year: null,
  cell: null,                       // last clicked {row, col, lngLat}
};
let map, ui;

const $ = (s) => document.querySelector(s);
const seg = (id) => [...document.querySelectorAll(`#${id} button`)];

export async function available() {
  try { const r = await fetch(APP + "app_meta.json", { method: "HEAD" }); return r.ok; } catch { return false; }
}

/* activate() can be called (a fast click, a story chapter) before init() has finished on map load:
   it waits here instead of silently no-opping, which left a dead layer until the next switch */
let readyDone;
const ready = new Promise((r) => (readyDone = r));

export async function init(mapRef) {
  try {
    map = mapRef;
    state.meta = await (await fetch(APP + "app_meta.json")).json();
    ui = $("#timebar");
    seg("segSeason").forEach((b) => b.addEventListener("click", () => { setSeg("segSeason", b); state.season = b.dataset.v; refresh(); }));
    seg("segMode").forEach((b) => b.addEventListener("click", () => { setSeg("segMode", b); state.mode = b.dataset.v; refresh(); }));
    seg("segVar").forEach((b) => b.addEventListener("click", () => { setSeg("segVar", b); state.v = b.dataset.v; refresh(); }));
    $("#yearSlider").addEventListener("input", (e) => {
      if (VARS[state.active] && VARS[state.active].monthly) { state.month = +e.target.value; refreshMonthly(); }
      else { state.year = +e.target.value; refresh(false); }
    });
    $("#cellClose").addEventListener("click", () => ($("#cellPanel").hidden = true));
  } finally {
    readyDone();                           // resolve even on failure; activate then no-ops on !state.meta
  }
}

function setSeg(id, btn) {
  seg(id).forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
}

async function loadTif(name) {
  if (state.stacks.has(name)) return state.stacks.get(name);
  const buf = await (await fetch(APP + name)).arrayBuffer();
  const tif = await GeoTIFF.fromArrayBuffer(buf);
  const img = await tif.getImage();
  const bands = await img.readRasters();
  const entry = { bands, width: img.getWidth(), height: img.getHeight() };
  state.stacks.set(name, entry);
  return entry;
}

async function ensureNormals() {
  if (!state.normals) state.normals = await loadTif("normals.tif");
  if (!state.landmask) state.landmask = await loadTif("landmask.tif");
}

export async function activate(layerId) {
  await ready;                             // init() runs on map load; a faster click waits for it
  if (!state.meta) return;                 // init failed (no climate data): leave the layer off
  state.active = layerId;
  if (!VARS[layerId].vars.includes(state.v)) state.v = VARS[layerId].vars[0];
  if (VARS[layerId].monthly) {
    state.mode = "value";                  // a sticky anomaly mode must not leak into the SPI draw
    const months = spiMonths();
    if (state.month == null || state.month >= months.length) state.month = months.length - 1;
    $("#segVar").hidden = true; $("#segSeason").hidden = true; $("#segMode").hidden = true;
    ui.hidden = false;
    await ensureNormals();
    await refreshMonthly();
    return;
  }
  $("#segSeason").hidden = false; $("#segMode").hidden = false;
  const years = state.meta.years[`${state.v}_annual`];
  if (state.year == null || !years.includes(state.year)) state.year = years[years.length - 1];
  $("#segVar").hidden = VARS[layerId].vars.length < 2;
  seg("segVar").forEach((b, i) => { b.hidden = !VARS[layerId].vars.includes(b.dataset.v); });
  setSeg("segVar", seg("segVar").find((b) => b.dataset.v === state.v));
  setSeg("segSeason", seg("segSeason").find((b) => b.dataset.v === state.season) || seg("segSeason")[0]);
  setSeg("segMode", seg("segMode").find((b) => b.dataset.v === state.mode) || seg("segMode")[0]);
  ui.hidden = false;
  await ensureNormals();
  await refresh();
}

export function deactivate() {
  state.active = null;
  if (!ui) return;                         // init() (map load) not done yet; nothing is shown anyway
  ui.hidden = true;
  $("#cellPanel").hidden = true;
  if (map.getLayer("climate")) map.setLayoutProperty("climate", "visibility", "none");
}

function key() { return `${state.v}_${state.season}`; }

/* anomaly is undefined for tmax/tmin (normals are precip & tmean only) */
function modeAllowed() { return state.mode === "value" || state.v === "precip" || state.v === "tmean"; }

async function refresh(resetSlider = true) {
  const active = state.active;
  if (!active || VARS[active].monthly) return;
  if (!modeAllowed()) { state.mode = "value"; setSeg("segMode", seg("segMode")[0]); }
  seg("segMode")[1].disabled = !(state.v === "precip" || state.v === "tmean");
  const years = state.meta.years[key()];
  const sl = $("#yearSlider");
  sl.min = years[0]; sl.max = years[years.length - 1];
  if (!years.includes(state.year)) state.year = years[years.length - 1];
  sl.value = state.year;

  const stack = await loadTif(`${key()}.tif`);
  if (state.active !== active) return;      // switched layer while the stack loaded: stale draw
  const bi = years.indexOf(state.year);
  const band = stack.bands[bi];
  const { lo, hi, ramp, fmt, label } = displaySpec();
  drawRaster(band, lo, hi, ramp);
  $("#timeLabel").innerHTML = `<strong>${state.year}</strong> · ${seasonName()} ${VARS[state.active].how}`;
  renderLegend(lo, hi, ramp, fmt, label);
  if (state.cell) showCell(state.cell.lngLat, false);
}

function seasonName() { return state.season === "annual" ? "annual" : state.season.toUpperCase(); }

async function refreshMonthly() {
  const months = spiMonths();
  const sl = $("#yearSlider");
  sl.min = 0; sl.max = months.length - 1; sl.value = state.month;
  const stack = await loadTif("spi3.tif");
  if (state.active !== "spi3") return;      // switched layer while the stack loaded: stale draw
  drawRaster(stack.bands[state.month], -3, 3, RAMPS.precip_anom, 0.01);   // SPI stored x100
  const prov = state.month >= months.length - 3 ? " · provisional" : "";
  $("#timeLabel").innerHTML = `<strong>${months[state.month]}</strong> · SPI-3${prov}`;
  const box = $("#legend");
  box.innerHTML = "";
  const h3 = document.createElement("h3"); h3.textContent = "SPI-3 — 3-month standardized precipitation"; box.append(h3);
  const steps = document.createElement("div"); steps.className = "steps";
  for (let i = 0; i < 24; i++) { const sp = document.createElement("span");
    const c = colToRgb(RAMPS.precip_anom, i / 23); sp.style.background = `rgb(${c[0]|0},${c[1]|0},${c[2]|0})`; steps.append(sp); }
  box.append(steps);
  const axis = document.createElement("div"); axis.className = "axis";
  axis.innerHTML = "<span>−3 dry</span><span>+3 wet</span>"; box.append(axis);
  const src = document.createElement("p"); src.className = "src";
  src.textContent = "Gamma fit (Thom), calibration 1991–2020 · CHIRPS v3.0 · 0.05°"; box.append(src);
  box.hidden = false;
  if (state.cell) showCellSpi(state.cell.lngLat, false);
}

async function showCellSpi(lngLat, open = true) {
  const rc = cellAt(lngLat);
  if (!rc) return;
  state.cell = { ...rc, lngLat };
  const months = spiMonths();
  const n = months.length;
  const off = (rc.row * state.meta.width + rc.col) * n * 2;
  const r = await fetch(APP + "spi3_cells.bin", { headers: { Range: `bytes=${off}-${off + n * 2 - 1}` } });
  const cell = new Int16Array(await r.arrayBuffer());
  if (!state.spiBasin) state.spiBasin = (await (await fetch(dataUrl("series/spi3_basin.json"))).json()).monthly;
  const basin = months.map((m) => state.spiBasin[m] ?? null);
  const val = (x) => (x === NODATA ? null : x / 100);
  const cur = val(cell[state.month]);
  const basinCur = basin[state.month];

  const panel = $("#cellPanel"), body = $("#cellBody");
  window.closeFloatingPanels?.("cellPanel");
  $("#cellTitle").textContent = `SPI-3 at ${window.fmtCoord(lngLat.lat, lngLat.lng)}`;
  $("#cellHint").textContent = "SPI-3 from CHIRPS v3.0 · calibration 1991–2020";
  body.innerHTML = "";
  const qc = await loadTif("spi3_qc.tif");
  const calMonth = +months[state.month].slice(5) - 1;
  const idx = rc.row * state.meta.width + rc.col;
  const normalMm = qc.bands[calMonth][idx] / 10;
  const q0pct = qc.bands[12 + calMonth][idx] / 10;
  const lowNormal = normalMm < 30 || q0pct > 20;
  const provisional = state.month >= months.length - 3;
  const kpis = document.createElement("div"); kpis.className = "kpis";
  kpis.innerHTML = `
    <div class="lead"><div class="label">SPI-3 · ${months[state.month]}${provisional ? " (provisional)" : ""}</div>
      <div class="value num">${cur == null ? "—" : cur.toFixed(2)}</div>
      <div class="sub">${cur == null ? "" : spiCat(cur)}</div></div>
    <div><div class="label">Basin mean (land)</div>
      <div class="value num">${basinCur == null ? "—" : basinCur.toFixed(2)}</div></div>
    <div><div class="label">Calibration</div><div class="value num" style="font-size:16px">1991–2020</div></div>`;
  body.append(kpis);
  if (lowNormal) {
    const warn = document.createElement("div"); warn.className = "empty";
    warn.textContent = `Low-rainfall season here (normal 3-month total ${normalMm.toFixed(0)} mm): ` +
      "SPI values in this window are statistically fragile.";
    body.append(warn);
  }
  if (provisional) {
    const pw = document.createElement("p"); pw.className = "meta";
    pw.innerHTML = '<span class="pill review">provisional</span> The latest 2–3 CHIRPS months may be revised.';
    body.append(pw);
  }
  const block = document.createElement("div"); block.className = "chart-block";
  const h = document.createElement("h3"); h.textContent = "Last 15 years, this cell vs basin land mean"; block.append(h);
  const lg = document.createElement("div"); block.append(lg);
  const mount = document.createElement("div"); block.append(mount);
  const k0 = Math.max(0, n - 180);
  const lab = months.slice(k0).map((m) => (m.endsWith("-01") && +m.slice(0, 4) % 3 === 0 ? m.slice(0, 4) : ""));
  Charts.line(mount, {
    labels: lab, height: 180, format: (v) => v.toFixed(1), min: -3, max: 3,
    series: [{ name: "this cell", values: Array.from(cell.slice(k0)).map(val) },
             { name: "basin mean", values: basin.slice(k0), colour: "#8a8a8a" }],
    legend: lg,
  });
  const meta = document.createElement("p"); meta.className = "meta";
  meta.textContent = "SPI-3 from CHIRPS v3.0 · gamma fit (Thom 1958), zero-rain mixed distribution";
  block.append(meta);
  body.append(block);
  if (open) panel.hidden = false;
}

function normalBand() {
  const nk = `${state.v === "precip" ? "precip" : "tmean"}_${state.season}`;
  const labels = ["precip_annual", "precip_mam", "precip_ond", "tmean_annual", "tmean_mam", "tmean_ond"];
  return state.normals.bands[labels.indexOf(nk)];
}

function displaySpec() {
  const vdef = VARS[state.active];
  if (state.mode === "anomaly") {
    const r = state.meta.ranges[`${state.v}_${state.season}_anom`];
    const c = vdef.anom.centre;
    const d = Math.max(Math.abs(r[0] - c), Math.abs(r[1] - c));
    return { lo: c - d, hi: c + d, ramp: RAMPS[state.active === "precip" ? "precip_anom" : "temp_anom"],
             fmt: (v) => v.toFixed(0), label: vdef.anom.units + ` (${state.meta.normal})` };
  }
  const r = state.meta.ranges[key()];
  return { lo: r[0], hi: r[1], ramp: RAMPS[state.active === "precip" ? "precip" : "temp"],
           fmt: (v) => v.toFixed(0), label: `${vdef.units} · ${seasonName()} ${vdef.how}` };
}

function colToRgb(ramp, t) {
  const x = Math.min(Math.max(t, 0), 1) * (ramp.length - 1);
  const i = Math.floor(x), f = x - i;
  const a = ramp[Math.min(i, ramp.length - 1)], b = ramp[Math.min(i + 1, ramp.length - 1)];
  const h = (s) => [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)];
  const [r1, g1, b1] = h(a), [r2, g2, b2] = h(b);
  return [r1 + (r2 - r1) * f, g1 + (g2 - g1) * f, b1 + (b2 - b1) * f];
}

/* MapLibre does not drape image/canvas sources over 3D terrain, so the grid is drawn as one
   GeoJSON fill feature per 0.05 deg cell (fill layers drape correctly). Geometry is built once;
   each refresh only recomputes the per-cell colour. */
let cellGeom = null;
function buildCellGeometry() {
  const [a, , c, , e, f] = state.meta.transform;
  const feats = [];
  for (let r = 0; r < state.meta.height; r++) {
    for (let q = 0; q < state.meta.width; q++) {
      const x0 = c + q * a, y0 = f + r * e;
      feats.push({ type: "Feature", id: r * state.meta.width + q,
                   properties: { c: "rgba(0,0,0,0)" },
                   geometry: { type: "Polygon",
                               coordinates: [[[x0, y0], [x0 + a, y0], [x0 + a, y0 + e], [x0, y0 + e], [x0, y0]]] } });
    }
  }
  return { type: "FeatureCollection", features: feats };
}

function drawRaster(band, lo, hi, ramp, scale = SCALE) {
  if (!cellGeom) cellGeom = buildCellGeometry();
  // anomaly only for variables that have a normal (precip, tmean); never for SPI, whatever the mode says
  const norm = state.mode === "anomaly" && VARS[state.active]?.anom ? normalBand() : null;
  for (let i = 0; i < band.length; i++) {
    let col = null;
    let v = band[i];
    if (v !== NODATA) {
      v *= scale;
      if (norm) {
        const n = norm[i];
        if (n === NODATA) { v = null; } else { v = state.active === "precip" ? (100 * v) / (n * SCALE) : v - n * SCALE; }
      }
      if (v != null) {
        const [r, g, b] = colToRgb(ramp, (v - lo) / (hi - lo));
        const onWater = state.landmask && state.landmask.bands[0][i] === 20;
        col = onWater ? `rgba(${r | 0},${g | 0},${b | 0},0.35)`   // lake rainfall less reliable: faded
                      : `rgb(${r | 0},${g | 0},${b | 0})`;
      }
    }
    cellGeom.features[i].properties.c = col || "rgba(0,0,0,0)";
  }
  if (!map.getSource("climate-grid")) {
    map.addSource("climate-grid", { type: "geojson", data: cellGeom });
    map.addLayer({ id: "climate", type: "fill", source: "climate-grid",
                   paint: { "fill-color": ["get", "c"], "fill-opacity": 0.78, "fill-antialias": false } }, "dim");
  } else {
    map.getSource("climate-grid").setData(cellGeom);
  }
  map.setLayoutProperty("climate", "visibility", "visible");
}

function renderLegend(lo, hi, ramp, fmt, label) {
  const box = $("#legend");
  box.innerHTML = "";
  const h3 = document.createElement("h3");
  h3.textContent = `${VAR_LABEL[state.v]} — ${label}`;
  box.append(h3);
  const steps = document.createElement("div"); steps.className = "steps";
  for (let i = 0; i < 24; i++) {
    const s = document.createElement("span");
    const [r, g, b] = colToRgb(ramp, i / 23);
    s.style.background = `rgb(${r | 0},${g | 0},${b | 0})`;
    steps.append(s);
  }
  box.append(steps);
  const axis = document.createElement("div"); axis.className = "axis";
  axis.innerHTML = `<span>${fmt(lo)}</span><span>${fmt(hi)}</span>`;
  box.append(axis);
  const src = document.createElement("p"); src.className = "src";
  src.textContent = `${VARS[state.active].source} · 0.05° (~5.5 km)` +
    (state.active === "precip" ? " · satellite rainfall over the lake is less reliable" : "");
  box.append(src);
  box.hidden = false;
}

/* ---------------- click: one range request per cell ---------------- */
export function cellAt(lngLat) {
  const [a, , c, , e, f] = state.meta.transform;
  const col = Math.floor((lngLat.lng - c) / a);
  const row = Math.floor((lngLat.lat - f) / e);
  if (row < 0 || col < 0 || row >= state.meta.height || col >= state.meta.width) return null;
  return { row, col };
}

export async function showCell(lngLat, open = true) {
  if (VARS[state.active] && VARS[state.active].monthly) return showCellSpi(lngLat, open);
  const rc = cellAt(lngLat);
  if (!rc) return;
  state.cell = { ...rc, lngLat };
  const nMonths = 548;
  const file = state.active === "precip" ? "precip_cells.bin" : "tmean_cells.bin";
  const off = (rc.row * state.meta.width + rc.col) * nMonths * 2;
  const r = await fetch(APP + file, { headers: { Range: `bytes=${off}-${off + nMonths * 2 - 1}` } });
  const series = new Int16Array(await r.arrayBuffer());

  const months = [];
  const y0 = 1981;
  const monthsOf = (y) => series.slice((y - y0) * 12, (y - y0) * 12 + 12);
  const val = (x) => (x === NODATA ? null : x * SCALE);
  const agg = (vals) => {
    const sel = state.season === "annual" ? vals : [...vals].filter((_, i) =>
      (state.season === "mam" ? [2, 3, 4] : [9, 10, 11]).includes(i));
    const nums = [...sel].map(val);
    if (nums.some((v) => v == null)) return null;
    return state.active === "precip" ? nums.reduce((a, b) => a + b, 0) : nums.reduce((a, b) => a + b, 0) / nums.length;
  };
  const yearVal = agg(monthsOf(state.year));
  const normalYears = [];
  for (let y = 1991; y <= 2020; y++) normalYears.push(agg(monthsOf(y)));
  const normal = normalYears.every((v) => v != null) ? normalYears.reduce((a, b) => a + b, 0) / 30 : null;

  const vdef = VARS[state.active];
  const unit = vdef.units;
  const fmtV = (v) => (v == null ? "—" : state.active === "precip" ? Math.round(v).toLocaleString() : v.toFixed(1));
  const anomTxt = (yearVal != null && normal != null)
    ? (state.active === "precip" ? `${Math.round((100 * yearVal) / normal)} % of normal`
                                 : `${(yearVal - normal) >= 0 ? "+" : ""}${(yearVal - normal).toFixed(1)} °C vs normal`) : "—";

  const panel = $("#cellPanel");
  const body = $("#cellBody");
  window.closeFloatingPanels?.("cellPanel");
  $("#cellTitle").textContent = `${VAR_LABEL[state.v]} at ${window.fmtCoord(lngLat.lat, lngLat.lng)}`;
  $("#cellHint").textContent = VARS[state.active].source;
  const lmv = state.landmask.bands[0][rc.row * state.meta.width + rc.col];
  const onWater = lmv === 20;
  body.innerHTML = "";
  const kpis = document.createElement("div"); kpis.className = "kpis";
  kpis.innerHTML = `
    <div class="lead"><div class="label">${seasonName()} ${vdef.how} · ${state.year}</div>
      <div class="value num">${fmtV(yearVal)} <span class="unit">${unit}</span></div></div>
    <div><div class="label">Normal ${state.meta.normal}</div>
      <div class="value num">${fmtV(normal)} <span class="unit">${unit}</span></div></div>
    <div><div class="label">This year</div><div class="value num" style="font-size:18px">${anomTxt}</div></div>`;
  body.append(kpis);
  if (onWater && state.active === "precip") {
    const note = document.createElement("div"); note.className = "empty";
    note.textContent = "Lake-surface cell: satellite rainfall estimates over open water are less reliable.";
    body.append(note);
  }
  if (state.active === "temperature" && state.v !== "tmean") {
    const note = document.createElement("p"); note.className = "meta";
    note.textContent = "The series below shows Tmean = (Tmax+Tmin)/2; the map shows " + VAR_LABEL[state.v] + ".";
    body.append(note);
  }

  const block = document.createElement("div"); block.className = "chart-block";
  const h = document.createElement("h3");
  h.textContent = `${state.year} by month vs the ${state.meta.normal} monthly normal (${unit})`;
  block.append(h);
  const lg = document.createElement("div"); block.append(lg);
  const mount = document.createElement("div"); block.append(mount);
  const yearMon = [...monthsOf(state.year)].map(val);
  const normMon = MONTH_NAMES.map((_, m) => {
    let s = 0, n = 0;
    for (let y = 1991; y <= 2020; y++) { const v = val(monthsOf(y)[m]); if (v != null) { s += v; n++; } }
    return n ? +(s / n).toFixed(1) : null;
  });
  Charts.line(mount, {
    labels: MONTH_NAMES, height: 180, format: (v) => (state.active === "precip" ? Math.round(v) : v.toFixed(1)),
    series: [{ name: String(state.year), values: yearMon },
             { name: `normal ${state.meta.normal}`, values: normMon, colour: "#8a8a8a", dash: true }],
    legend: lg,
  });
  const meta = document.createElement("p"); meta.className = "meta";
  meta.textContent = `${vdef.source}, 0.05° cell · monthly series 1981–2026`;
  block.append(meta);
  body.append(block);
  if (open) panel.hidden = false;
}

export function isActive() { return state.active != null; }

export function presetFromHash(h) {
  if (h.get("var")) state.v = h.get("var");
  if (h.get("season")) state.season = h.get("season");
  if (h.get("mode")) state.mode = h.get("mode");
  if (h.get("year")) state.year = +h.get("year");
}
