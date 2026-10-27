/* Population (exposure input) and tree-cover loss layers.
   - population: OrRd log-scaled tiles; click reads the exact 100 m cell from the COG by range request.
   - forest loss: loss YEAR is encoded in the tiles' red channel; MapLibre's raster-color styles it
     cumulatively up to the slider year (runtime-checked; without support the layer is disabled). */

import { dataUrl } from "./config.js";
import { setVisibility } from "./layers.js";
const $ = (s) => document.querySelector(s);

const state = { active: null, year: null, reg: {}, tiff: null, img: null, series: null, sub: null };
let map, timebar;
/* init() runs in the map 'load' handler; a story chapter or a fast click can call activate() first */
let readyDone;
const ready = new Promise((r) => (readyDone = r));

export function init(mapRef, registry) {
  map = mapRef;
  state.reg = registry;
  timebar = $("#timebar");
  $("#yearSlider").addEventListener("input", onSlider);
  readyDone();
}

function epochs() { return state.reg.forest_loss?.epochs || []; }

function labelForest() {
  $("#timeLabel").innerHTML = `<strong>≤ ${state.year}</strong> · cumulative tree-cover loss (5-yr steps)`;
}

function onSlider(e) {
  if (state.active !== "forest_loss") return;
  state.year = epochs()[+e.target.value];
  applyForestEpoch();
  labelForest();
  if (state.lastClick) showForestPanel(state.lastClick, false);
}

export function isActive() { return state.active != null; }

export async function activate(id) {
  state.active = id;
  await ready;
  if (state.active !== id) return;          // switched away while waiting
  if (id === "population") {
    timebar.hidden = true;
    renderPopLegend();
  } else {
    const es = epochs();
    if (!es.includes(state.year)) state.year = es[es.length - 1];
    ["segVar", "segSeason", "segMode"].forEach((x) => ($("#" + x).hidden = true));
    const sl = $("#yearSlider");
    sl.min = 0; sl.max = es.length - 1; sl.step = 1; sl.value = es.indexOf(state.year);
    timebar.hidden = false;
    labelForest();
    applyForestEpoch();
    renderForestLegend();
  }
}

export function deactivate() {
  if (state.active === "forest_loss" && map) hideForest();
  state.active = null;
  state.lastClick = null;
}

/* ---------------- forest: cumulative loss as pre-rendered 5-year epoch layers ----------------
   (MapLibre has no per-value raster styling, so each epoch is its own tile set) */
function applyForestEpoch() {
  for (const y of epochs()) {
    const id = "loss-le-" + y;
    setVisibility(map, id, y === state.year ? "visible" : "none");
  }
}

export function hideForest() {
  for (const y of epochs()) {
    const id = "loss-le-" + y;
    setVisibility(map, id, "none");
  }
}

/* ---------------- legends ---------------- */
const ORRD = ["#fff3e5", "#fdd49e", "#fdbb84", "#fc8d59", "#ef6548", "#d7301f", "#b30000", "#7f0000"];

function legendBox(title, colors, lo, hi, srcText) {
  const box = $("#legend");
  box.innerHTML = "";
  const h3 = document.createElement("h3"); h3.textContent = title; box.append(h3);
  const steps = document.createElement("div"); steps.className = "steps";
  colors.forEach((c) => { const s = document.createElement("span"); s.style.background = c; steps.append(s); });
  box.append(steps);
  const axis = document.createElement("div"); axis.className = "axis";
  axis.innerHTML = `<span>${lo}</span><span>${hi}</span>`; box.append(axis);
  const src = document.createElement("p"); src.className = "src"; src.textContent = srcText; box.append(src);
  box.hidden = false;
}

function renderPopLegend() {
  legendBox("Population — persons per ~100 m cell (log scale)", ORRD, "1", "≥3000",
            (state.reg.population?.source || "WorldPop 2020 constrained") +
            " · exposure input, not risk");
}

function renderForestLegend() {
  const r = state.reg.forest_loss || {};
  legendBox(`Tree-cover loss 2001–${state.year}, 5-yr steps (cover 2000 ≥ 30 %)`,
            ["rgba(178,24,43,0.9)"], "loss", "",
            (r.source || "Hansen GFC") + " · detection improved ~2011–13; " +
            "annual values not strictly comparable · tree-cover loss, not deforestation");
}

/* ---------------- clicks ---------------- */
export async function onClick(lngLat) {
  if (state.active === "population") return showPopPanel(lngLat);
  if (state.active === "forest_loss") return showForestPanel(lngLat, true);
}

async function popTiff() {
  if (!state.img) {
    state.tiff = await GeoTIFF.fromUrl(dataUrl("query/pop_100m.tif"), { allowFullFile: false });
    state.img = await state.tiff.getImage();
  }
  return state.img;
}

async function showPopPanel(lngLat) {
  const img = await popTiff();
  const [ox, rx, , oy, , ry] = [img.getOrigin()[0], img.getResolution()[0], 0,
                                img.getOrigin()[1], 0, img.getResolution()[1]];
  const col = Math.floor((lngLat.lng - ox) / rx);
  const row = Math.floor((lngLat.lat - oy) / ry);
  if (col < 0 || row < 0 || col >= img.getWidth() || row >= img.getHeight()) return;
  const win = [Math.max(col - 1, 0), Math.max(row - 1, 0), Math.min(col + 2, img.getWidth()), Math.min(row + 2, img.getHeight())];
  const data = (await img.readRasters({ window: win }))[0];
  const wpx = win[2] - win[0];
  const centre = data[(row - win[1]) * wpx + (col - win[0])];
  let block = 0;
  for (const v of data) if (v > 0) block += v;

  const p = $("#popover");
  window.closeFloatingPanels?.("popover");
  const fmt = (v) => (v < 0 ? "no data / uninhabited" : Math.round(v).toLocaleString());
  p.innerHTML = `<h3>Population (exposure input)</h3>
    <div class="row"><span>This ~100 m cell</span><span>${fmt(centre)}</span></div>
    <div class="row"><span>3×3 cells (~300 m)</span><span>${Math.round(block).toLocaleString()}</span></div>
    <p class="meta">WorldPop 2020 constrained · modelled counts · people in place, not risk</p>`;
  positionPopover(p, lngLat);
}

function positionPopover(p, lngLat) {
  const pt = map.project(lngLat);
  const r = $("#map").getBoundingClientRect();
  p.style.left = Math.min(pt.x + 12, r.width - 300) + "px";
  p.style.top = Math.min(pt.y + 12, r.height - 160) + "px";
  p.hidden = false;
}

async function showForestPanel(lngLat, open) {
  state.lastClick = lngLat;
  if (!state.series) state.series = await (await fetch(dataUrl("series/forest_loss.json"))).json();
  if (state.sub == null) {
    try { state.sub = await (await fetch(dataUrl("vectors/subbasins.geojson"))).json(); }
    catch { state.sub = false; }
  }
  let region = "Lake Victoria Basin";
  if (state.sub) {
    for (const f of state.sub.features) {
      if (pointInPoly(lngLat, f.geometry)) { region = f.properties.name; break; }
    }
  }
  const yearly = state.series.regions[region] || state.series.regions["Lake Victoria Basin"];
  const years = Object.keys(yearly);
  const vals = years.map((y) => yearly[y]);
  const upto = years.filter((y) => +y <= state.year).reduce((a, y) => a + yearly[y], 0);
  const total = vals.reduce((a, b) => a + b, 0);

  const panel = $("#cellPanel"), body = $("#cellBody");
  window.closeFloatingPanels?.("cellPanel");
  $("#cellTitle").textContent = `Tree-cover loss · ${region}`;
  $("#cellHint").textContent = state.reg.forest_loss?.source || "Hansen GFC";
  body.innerHTML = "";
  const kpis = document.createElement("div"); kpis.className = "kpis";
  kpis.innerHTML = `
    <div class="lead"><div class="label">Loss 2001–${state.year}</div>
      <div class="value num">${Math.round(upto).toLocaleString()} <span class="unit">km²</span></div></div>
    <div><div class="label">Full record</div>
      <div class="value num">${Math.round(total).toLocaleString()} <span class="unit">km²</span></div></div>
    <div><div class="label">Cover threshold</div><div class="value num" style="font-size:16px">≥30 % (2000)</div></div>`;
  body.append(kpis);
  const block = document.createElement("div"); block.className = "chart-block";
  const h = document.createElement("h3"); h.textContent = `Annual tree-cover loss, ${region} (km²)`; block.append(h);
  const mount = document.createElement("div"); block.append(mount);
  Charts.bars(mount, {
    labels: years.map((y) => (+y % 5 === 0 ? y : "")), values: vals, height: 170,
    format: (v) => Math.round(v).toLocaleString(),
    highlight: years.indexOf(String(state.year)),
  });
  const meta = document.createElement("p"); meta.className = "meta";
  meta.textContent = `${state.series.version} · ${state.series.note}`;
  block.append(meta);
  body.append(block);
  if (open) panel.hidden = false;
}

function pointInPoly(lngLat, geom) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  for (const poly of polys) {
    let inside = false;
    const ring = poly[0];
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > lngLat.lat) !== (yj > lngLat.lat) &&
          lngLat.lng < ((xj - xi) * (lngLat.lat - yi)) / (yj - yi) + xi) inside = !inside;
    }
    if (inside) return true;
  }
  return false;
}
