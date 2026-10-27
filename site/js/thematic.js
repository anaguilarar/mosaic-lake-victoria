/* Year-layer thematics: land cover (Esri/IO), fire density (VIIRS S-NPP), fire points, burned area
   (MCD64A1). Each is a set of per-year tile layers switched by the shared time bar, with a legend
   and a click panel fed from the registry and the series JSONs. */

import { dataUrl } from "./config.js";
import { setVisibility } from "./layers.js";
const $ = (s) => document.querySelector(s);

const state = { reg: {}, active: null, year: {}, pointsYear: null, series: {}, lulcTiff: null };
let map, timebar;

const DEFS = {
  landcover: { group: "Land", prefix: "lulc-", urlKey: ["landcover", "urls", "tiles"],
               yearsKey: ["landcover", "years"] },
  worldcover: { group: "Land", static: true, layerId: "worldcover" },
  fire: { group: "Fire", prefix: "fired-", urlKey: ["fire", "urls", "density"],
          yearsKey: ["fire", "years"] },
  burned_area: { group: "Fire", prefix: "burned-", urlKey: ["burned_area", "urls", "tiles"],
                 yearsKey: ["burned_area", "years"] },
};

const get = (o, path) => path.reduce((a, k) => (a ? a[k] : undefined), o);

export function layersFor(registry, pmUrl) {
  /* sources+layers for every per-year tile set, all hidden; called from initMap */
  state.reg = registry;
  const sources = {}, layers = [];
  for (const [id, d] of Object.entries(DEFS)) {
    if (d.static) continue;                      // static layers (WorldCover) have their own source in app.js
    const urls = get(registry, d.urlKey) || {};
    for (const [y, f] of Object.entries(urls)) {
      const lid = d.prefix + y;
      sources[lid] = { type: "raster", url: pmUrl(f), tileSize: 256 };
      layers.push({ id: lid, type: "raster", source: lid, layout: { visibility: "none" },
                    paint: { "raster-resampling": "nearest",
                             "raster-opacity": id === "landcover" ? 0.8 : 0.85 } });
    }
  }
  return { sources, layers };
}

/* init() runs in the map 'load' handler; a story chapter or a fast click can call activate() first */
let readyDone;
const ready = new Promise((r) => (readyDone = r));

export function init(mapRef) {
  map = mapRef;
  timebar = $("#timebar");
  readyDone();
  $("#yearSlider").addEventListener("input", (e) => {
    if (!state.active) return;
    const years = get(state.reg, DEFS[state.active].yearsKey) || [];
    state.year[state.active] = years[+e.target.value];
    applyYear();
    label();
    if (state.lastClick) showPanel(state.lastClick, false);
  });
}

export function isActive() { return state.active != null; }

export async function activate(id) {
  state.active = id;
  await ready;
  if (state.active !== id) return;          // switched away while waiting
  const d = DEFS[id];
  if (d.static) {                                   // WorldCover: one year, no slider
    timebar.hidden = true;
    setVisibility(map, d.layerId, "visible");
    renderLegend();
    return;
  }
  const years = get(state.reg, d.yearsKey) || [];
  if (!years.includes(state.year[id])) state.year[id] = years[years.length - 1];
  ["segVar", "segSeason", "segMode"].forEach((x) => ($("#" + x).hidden = true));
  const sl = $("#yearSlider");
  sl.min = 0; sl.max = years.length - 1; sl.step = 1; sl.value = years.indexOf(state.year[id]);
  timebar.hidden = false;
  label();
  applyYear();
  renderLegend();
  if (id === "fire") await loadPoints();
}

export function deactivate() {
  if (!state.active) return;
  if (!map) { state.active = null; return; }   // activated before init(): nothing was drawn yet
  for (const d of Object.values(DEFS)) {
    if (d.static) {
      setVisibility(map, d.layerId, "none");
      continue;
    }
    hideAll(d);
  }
  setVisibility(map, "fire-points", "none");
  state.active = null;
  state.lastClick = null;
}

function hideAll(d) {
  for (const y of Object.keys(get(state.reg, d.urlKey) || {})) {
    const lid = d.prefix + y;
    setVisibility(map, lid, "none");
  }
}

function applyYear() {
  const d = DEFS[state.active];
  const cur = String(state.year[state.active]);
  for (const y of Object.keys(get(state.reg, d.urlKey) || {})) {
    const lid = d.prefix + y;
    setVisibility(map, lid, y === cur ? "visible" : "none");
  }
  if (state.active === "fire") loadPoints();
}

function label() {
  const names = { landcover: "land cover", fire: "active-fire density (S-NPP)", burned_area: "burned area" };
  $("#timeLabel").innerHTML = `<strong>${state.year[state.active]}</strong> · ${names[state.active]}`;
}

/* ---------------- fire points (zoom >= 10, selected year) ---------------- */
async function loadPoints() {
  const y = state.year.fire;
  const url = dataUrl(`fire/points_${y}.geojson`);
  if (state.pointsYear !== y) {
    try {
      const gj = await (await fetch(url)).json();
      if (!map.getSource("fire-points")) {
        map.addSource("fire-points", { type: "geojson", data: gj });
        map.addLayer({ id: "fire-points", type: "circle", source: "fire-points",
          minzoom: (state.reg.fire?.points_from_zoom ?? 10),
          paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 13, 4.5],
                   "circle-color": "#e55064", "circle-opacity": 0.75,
                   "circle-stroke-color": "#7f1d2e", "circle-stroke-width": 0.5 } },
          map.getLayer("labels-start") ? "labels-start" : undefined);   // reference labels stay on top
      } else {
        map.getSource("fire-points").setData(gj);
      }
      state.pointsYear = y;
    } catch { /* points file missing: density still works */ }
  }
  if (map.getLayer("fire-points")) {
    map.setLayoutProperty("fire-points", "visibility", state.active === "fire" ? "visible" : "none");
  }
}

/* ---------------- legends ---------------- */
function legendBox(title, rows, srcText) {
  const box = $("#legend");
  box.innerHTML = "";
  const h3 = document.createElement("h3"); h3.textContent = title; box.append(h3);
  for (const [color, lab] of rows) {
    const r = document.createElement("div");
    r.style.cssText = "display:flex;align-items:center;gap:7px;margin:2px 0;font-size:12px";
    const sw = document.createElement("span");
    sw.style.cssText = `width:13px;height:13px;border-radius:3px;background:${color};flex:none`;
    r.append(sw, document.createTextNode(lab));
    box.append(r);
  }
  const src = document.createElement("p"); src.className = "src"; src.textContent = srcText;
  box.append(src);
  box.hidden = false;
}

const XPRODUCT_NOTE = "Class definitions differ: IO ‘Rangeland’ = WorldCover grassland + shrubland; "
  + "colours follow each product’s official palette.";
const WC_IN_BASIN = [10, 20, 30, 40, 50, 60, 80, 90];   // classes present in the basin

function renderLegend() {
  const y = state.year[state.active];
  if (state.active === "worldcover") {
    const cls = state.reg.worldcover?.classes || {};
    legendBox("Land cover 2021 (ESA WorldCover v200)",
      WC_IN_BASIN.filter((v) => cls[v]).map((v) => [`rgb(${cls[v].rgb.join(",")})`, cls[v].name]),
      "10 m shown at 30 m · CC BY 4.0 · " + XPRODUCT_NOTE);
  } else if (state.active === "landcover") {
    const cls = state.reg.landcover?.classes || {};
    legendBox(`Land cover ${y} (Esri/Impact Observatory)`,
      Object.values(cls).filter((c) => !["Snow/ice", "Clouds"].includes(c.name))
        .map((c) => [`rgb(${c.rgb.join(",")})`, c.name]),
      "10 m shown at 30 m · CC BY 4.0 · 2017→2023 change is indicative (classifier "
      + "year-to-year differences; Kerner et al. 2023) · " + XPRODUCT_NOTE);
  } else if (state.active === "fire") {
    const lg = state.reg.fire?.legend_steps || {};
    const rows = (lg.colors || []).map((c, i) => [c, `≤ ${lg.breaks[i]} fires/km²`]);
    legendBox(`Active fires ${y} — density (S-NPP only)`, rows,
      "VIIRS 375 m, confidence nominal/high · points from zoom 10 incl. NOAA-20 · savanna and "
      + "crop-residue burning; charcoal not detected reliably");
  } else {
    legendBox(`Burned at least once in ${y}`, [["rgb(120,32,18)", "burned (MCD64A1, ~500 m)"]],
      "MODIS MCD64A1 v6.1 · misses small/low-intensity burns; cloud limits wet-season detection");
  }
}

/* ---------------- clicks ---------------- */
export async function onClick(lngLat) { return showPanel(lngLat, true); }

async function classAt(lngLat, which) {
  const key = which + "Tiff";
  if (!state[key]) {
    const url = which === "lulc" ? "query/lulc_stack_30m.tif" : "query/worldcover_30m.tif";
    const tif = await GeoTIFF.fromUrl(dataUrl(url), { allowFullFile: false });
    state[key] = await tif.getImage();
  }
  const img = state[key];
  const [ox, oy] = img.getOrigin();
  const [rx, ry] = img.getResolution();
  const col = Math.floor((lngLat.lng - ox) / rx), row = Math.floor((lngLat.lat - oy) / ry);
  if (col < 0 || row < 0 || col >= img.getWidth() || row >= img.getHeight()) return null;
  const sample = which === "lulc" ? state.reg.landcover.years.indexOf(state.year.landcover) : 0;
  const d = await img.readRasters({ window: [col, row, col + 1, row + 1], samples: [sample] });
  return d[0][0];
}
const lulcClassAt = (lngLat) => classAt(lngLat, "lulc");

async function showPanel(lngLat, open) {
  state.lastClick = lngLat;
  const panel = $("#cellPanel"), body = $("#cellBody");
  window.closeFloatingPanels?.("cellPanel");
  const y = state.year[state.active];

  if (state.active === "worldcover") {
    const v = await classAt(lngLat, "wc");
    const cls = state.reg.worldcover?.classes?.[v];
    $("#cellTitle").textContent = `WorldCover at ${window.fmtCoord(lngLat.lat, lngLat.lng)}`;
    $("#cellHint").textContent = state.reg.worldcover.source;
    body.innerHTML = "";
    const kpis = document.createElement("div"); kpis.className = "kpis";
    kpis.innerHTML = `
      <div class="lead"><div class="label">Class · 2021</div>
        <div class="value" style="font-size:20px">${cls ? cls.name : "no data"}</div></div>
      <div><div class="label">Product</div><div class="value" style="font-size:15px">ESA WorldCover v200</div></div>
      <div><div class="label">Licence</div><div class="value" style="font-size:15px">CC BY 4.0</div></div>`;
    body.append(kpis);
    const note = document.createElement("p"); note.className = "meta";
    note.textContent = XPRODUCT_NOTE;
    body.append(note);
    if (open) panel.hidden = false;
    return;
  }
  if (state.active === "landcover") {
    const v = await lulcClassAt(lngLat);
    const cls = state.reg.landcover?.classes?.[v];
    if (!state.series.lulc) state.series.lulc = await (await fetch(dataUrl("series/lulc_areas.json"))).json();
    const areas = state.series.lulc.areas[String(y)]["Lake Victoria Basin"];
    $("#cellTitle").textContent = `Land cover at ${window.fmtCoord(lngLat.lat, lngLat.lng)}`;
    $("#cellHint").textContent = state.reg.landcover.source;
    body.innerHTML = "";
    const kpis = document.createElement("div"); kpis.className = "kpis";
    kpis.innerHTML = `
      <div class="lead"><div class="label">Class · ${y}</div>
        <div class="value" style="font-size:20px">${cls ? cls.name : "no data"}</div></div>
      <div><div class="label">Basin area of class</div>
        <div class="value num" style="font-size:18px">${cls && areas[cls.name] != null
          ? Math.round(areas[cls.name]).toLocaleString() + " km²" : "—"}</div></div>
      <div><div class="label">Years</div><div class="value num" style="font-size:16px">2017–2023</div></div>`;
    body.append(kpis);
    const note = document.createElement("p"); note.className = "meta";
    note.textContent = state.reg.landcover.caveats;
    body.append(note);
  } else {
    if (!state.series.fire) state.series.fire = await (await fetch(dataUrl("series/fire.json"))).json();
    const f = state.series.fire;
    const isBurn = state.active === "burned_area";
    const data = isBurn ? f.burned_km2_basin : f.snpp_detections_basin;
    const years = Object.keys(data);
    $("#cellTitle").textContent = isBurn ? "Burned area · basin" : "Active fires · basin (S-NPP)";
    $("#cellHint").textContent = isBurn ? state.reg.burned_area.source : state.reg.fire.source;
    body.innerHTML = "";
    const kpis = document.createElement("div"); kpis.className = "kpis";
    const unit = isBurn ? "km²" : "detections";
    kpis.innerHTML = `
      <div class="lead"><div class="label">${y} · basin</div>
        <div class="value num">${Math.round(data[String(y)] ?? 0).toLocaleString()} <span class="unit">${unit}</span></div></div>
      <div><div class="label">Median year</div>
        <div class="value num" style="font-size:18px">${Math.round(median(Object.values(data))).toLocaleString()}</div></div>
      <div><div class="label">Record</div>
        <div class="value num" style="font-size:18px">${Math.round(Math.max(...Object.values(data))).toLocaleString()}</div></div>`;
    body.append(kpis);
    const block = document.createElement("div"); block.className = "chart-block";
    const h = document.createElement("h3");
    h.textContent = isBurn ? "Burned area per year (km²)" : "S-NPP detections per year (basin)";
    block.append(h);
    const mount = document.createElement("div"); block.append(mount);
    Charts.bars(mount, { labels: years.map((x) => (+x % 5 === 0 ? x : "")), values: Object.values(data),
                         height: 160, format: (v) => Math.round(v).toLocaleString(),
                         highlight: years.indexOf(String(y)) });
    const meta = document.createElement("p"); meta.className = "meta";
    meta.textContent = (isBurn ? state.reg.burned_area.caveats : f.caveats) || "";
    block.append(meta);
    body.append(block);
  }
  if (open) panel.hidden = false;
}

const median = (a) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };

export function presetFromHash(h) {
  if (h.get("year") && state.active) state.year[state.active] = +h.get("year");
}
