/* Basin Explorer — map-first app screen (achromatic-ledger).
   Static: PMTiles + GeoJSON + JSON read from the data root (site/js/config.js dataUrl). No backend. */

import * as climate from "./climate.js";
import * as compare from "./compare.js";
import * as land from "./land.js";
import * as stories from "./stories.js";
import * as thematic from "./thematic.js";

import { dataUrl, isWithheld } from "./config.js";
import { split as splitLazy, setVisibility } from "./layers.js";
const TILE_V = "13";   // bump to defeat stale HTTP caches after tile rebuilds
const fmtCoord = (lat, lng) =>
  `${Math.abs(lat).toFixed(2)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lng).toFixed(2)}° ${lng >= 0 ? "E" : "W"}`;
const closeFloating = (except) => {
  for (const id of ["popover", "cellPanel", "lakePanel", "aboutPanel", "storiesPanel"]) {
    if (id !== except) { const n = document.getElementById(id); if (n) n.hidden = true; }
  }
  if (except !== "storiesPanel") document.getElementById("storiesBtn")?.setAttribute("aria-expanded", "false");
};
const pmUrl = (f) => "pmtiles://" + new URL(dataUrl(f) + "?v=" + TILE_V, location.href).href;
const HUE = "#117A8D";   // MOSAIC teal-mid: water data in the brand water colour
const VIRIDIS10 = ["#45347f","#3b508a","#30688d","#267f8e","#1e978a","#27ad80","#4bc26c","#81d34c","#bfdf24","#fde724"];
const VIRIDIS7 = ["#45347f","#355c8c","#267f8e","#1fa286","#4bc26c","#9fd938","#fde724"];
const FREQ_STEPS = [1, 2, 5, 10, 20, 50, 100];

/* Thematic overlays: one active at a time (radio). `file` is checked before the item is offered. */
const OVERLAYS = [
  { id: "flood_years", group: "Flood hazard", title: "Years flooded", file: "tiles/flood_years.pmtiles",
    legend: { title: "Calendar years with ≥1 flood detection, 2016–2025", steps: VIRIDIS10,
              labels: ["1", "10"], note: "a pixel is coloured if any part of it flooded (highest years shown) · 0 years = transparent · where GFM excludes ≥50 % of observations, absence of floods is uncertain (see ‘Not assessed’)" } },
  { id: "flood_freq", group: "Flood hazard", title: "Flood frequency", file: "tiles/flood_freq.pmtiles",
    legend: { title: "Flood detections, % of valid observations", steps: VIRIDIS7, labels: ["≤1 %", "100 %"],
              note: "zoomed out, a pixel shows the highest frequency within it" } },
  /* the two seasonal frequencies are not rail entries: they sit behind the season switch that the
     Flood frequency legend shows (All / MAM / OND) */
  { id: "flood_freq_mam", group: "Flood hazard", title: "Flood frequency, long rains (MAM)", file: "tiles/flood_freq_mam.pmtiles",
    railHidden: true,
    legend: { title: "Flood detections, % of valid March–May observations", steps: VIRIDIS7, labels: ["≤1 %", "100 %"],
              note: "zoomed out, a pixel shows the highest frequency within it · needs ≥20 valid observations in the season · values on click are for the whole year" } },
  { id: "flood_freq_ond", group: "Flood hazard", title: "Flood frequency, short rains (OND)", file: "tiles/flood_freq_ond.pmtiles",
    railHidden: true,
    legend: { title: "Flood detections, % of valid October–December observations", steps: VIRIDIS7, labels: ["≤1 %", "100 %"],
              note: "zoomed out, a pixel shows the highest frequency within it · needs ≥20 valid observations in the season · values on click are for the whole year" } },
  { id: "flood_excl", group: "Flood hazard", title: "Not assessed (GFM exclusion)", file: "tiles/flood_excl.pmtiles",
    legend: { title: "Observations excluded by GFM, %", steps: ["#787878", "#4b4b4b", "#1e1e1e"],
              labels: ["50 %", "100 %"], note: "Flood layers carry no data here · also covers the Serengeti–Mara zone of radar look-alikes (not assessed, see the data report)" } },
  { id: "max_2020", group: "Flood hazard", title: "Max extent 2020", file: "tiles/max_2020.pmtiles",
    legend: { title: "Observed water outside the 2011–2015 lake (GLO-30 WBM), Apr–Jul 2020",
              steps: ["#1f5fbf"], labels: ["water observed at least once", ""],   // = the tiles' colour (06_prep_flood.py)
              note: "a pixel is coloured if any part of it flooded · Pietroiusti et al. (2024) map additional flooding east of the Speke Gulf head; neither "
                  + "GFM’s algorithms nor JRC Global Surface Water (May–June 2020) confirm it; April 2020 could "
                  + "not be checked optically because of cloud, and part of the area is outside GFM’s mappable zone." } },
  /*{ id: "max_2024", group: "Flood hazard", title: "Max extent 2024", file: "tiles/max_2024.pmtiles",
    legend: { title: "Observed water outside the 2011–2015 lake (GLO-30 WBM), Apr–May 2024",
              steps: [HUE], labels: ["water observed at least once", ""], note: "a pixel is coloured if any part of it flooded" } },*/
  { id: "precip", group: "Climate", title: "Precipitation", type: "climate", file: "climate/app/app_meta.json",
    swatch: "#434e6b" },
  { id: "temperature", group: "Climate", title: "Temperature", type: "climate", file: "climate/app/app_meta.json",
    swatch: "#e14c66" },
  { id: "spi3", group: "Climate", title: "Drought (SPI-3)", type: "climate", file: "climate/app/spi3.tif",
    swatch: "#35978f" },
  { id: "population", group: "Exposure", title: "Population", type: "land", file: "tiles/population.pmtiles",
    swatch: "#d7301f" },
  { id: "forest_loss", group: "Land", title: "Tree-cover loss", type: "land", file: "meta/layers.json",
    hasEpochs: true, swatch: "#b2182b" },
  { id: "landcover", group: "Land", title: "Land cover", type: "thematic", regKey: "landcover",
    swatch: "#e49635" },
  { id: "worldcover", group: "Land", title: "WorldCover 2021 (reference)", type: "thematic",
    regKey: "worldcover", swatch: "#397d49" },
  { id: "fire", group: "Fire", title: "Active fires", type: "thematic", regKey: "fire",
    swatch: "#e55064" },
  { id: "burned_area", group: "Fire", title: "Burned area", type: "thematic", regKey: "burned_area",
    swatch: "#782012" },
];

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const exists = async (url) => { try { const r = await fetch(url, { method: "HEAD" }); return r.ok; } catch { return false; } };
const getJSON = async (url) => { const r = await fetch(url); if (!r.ok) throw new Error(url); return r.json(); };

const state = { registry: {}, overlay: null, missing: [], floodSeason: "all" };
/* which tile layer the Flood frequency rail entry shows, per the legend's season switch */
const floodVariant = () =>
  state.floodSeason === "mam" ? "flood_freq_mam" : state.floodSeason === "ond" ? "flood_freq_ond" : "flood_freq";

/* ---------------- boot ---------------- */
window.addEventListener("error", (e) => notice("Script error: " + e.message));
window.addEventListener("unhandledrejection", (e) => notice("Error: " + (e.reason?.message || e.reason)));

(async function boot() {
  try {
    const reg = await getJSON(dataUrl("meta/layers.json"));
    for (const l of reg.layers) state.registry[l.id] = l;
  } catch { /* registry optional at this stage */ }

  const have = {};
  const regUrls = state.registry.flood_hazard?.urls || {};
  const probeList = ["tiles/terrain.pmtiles", "tiles/s2_rgb.pmtiles", "series/lake_level.json",
                     "vectors/rivers.geojson", "vectors/lake_detailed.geojson", "tiles/worldcover2021.pmtiles",
                     "tiles/osm_basemap.pmtiles", "vectors/basin.geojson", "vectors/basin_mask.geojson",
                     ...OVERLAYS.filter((o) => !o.id.startsWith("max_") && o.type !== "thematic").map((o) => o.file)];
  await Promise.all(probeList.map(async (f) => { have[f] = !isWithheld(f) && await exists(dataUrl(f)); }));
  for (const o of OVERLAYS) {
    if (o.id.startsWith("max_")) have[o.file] = Boolean(regUrls[o.id]);   // registry-driven: no 404 probes
  }
  state.have = have;

  const miss = [];
  if (!have["tiles/terrain.pmtiles"]) miss.push("terrain (prep 02)");
  if (!have["tiles/s2_rgb.pmtiles"]) miss.push("imagery (prep 03)");
  if (miss.length) notice(`Base tiles not built yet: ${miss.join(", ")}. The map shows data layers only.`);
  if (state.registry.flood_hazard?.placeholder) {
    notice("Flood layers show SYNTHETIC placeholder data until the GFM run lands.");
  }

  buildRail();
  buildAbout();
  initMap();
  wireUI();
  await stories.init({
    setOverlay, toggleLake,
    get map() { return map; },
    activeOverlay: () => state.overlay,
    overlayTitle: (id) => OVERLAYS.find((o) => o.id === id)?.title,
    overlayAvailable: (id) => {
      const item = document.querySelector(`.rail .item[data-overlay="${id}"]`);
      return Boolean(item && !item.classList.contains("unavailable"));
    },
    presetClimate: (p) => climate.presetFromHash(p),
  });
})();

function notice(msg) {
  const n = $("#notice");
  n.hidden = false;
  n.append(el("div", null, msg));
}

/* ---------------- layer rail ---------------- */
function buildRail() {
  const rail = $("#rail");
  const groups = new Map([["Base", []], ["Water", []], ["Flood hazard", []], ["Climate", []], ["Exposure", []], ["Land", []], ["Fire", []]]);
  const toggle = (title, swatch, ids, on, extra) => {
    const b = railItem(title, swatch, "");
    b.setAttribute("aria-pressed", String(on));
    b.addEventListener("click", () => {
      const now = b.getAttribute("aria-pressed") !== "true";
      b.setAttribute("aria-pressed", String(now));
      for (const id of ids) setVisibility(map, id, now ? "visible" : "none");
      extra?.(now);
      updateAttrib();
    });
    groups.get("Base").push(b);
    return b;
  };
  if (state.have["tiles/osm_basemap.pmtiles"]) {
    state.placeNames = true;
    toggle("Place names", "#ffffff", PLACE_IDS, true, (v) => (state.placeNames = v)).id = "placeNamesItem";
  }
  if (state.registry.admin_boundaries) {
    state.admin = false;
    toggle("Admin boundaries", "#c9ced2", ADMIN_IDS, false, (v) => (state.admin = v)).id = "adminItem";
  }

  if (state.have["vectors/rivers.geojson"]) {
    const rb = railItem("Rivers", HUE, "");
    rb.setAttribute("aria-pressed", "true");
    rb.addEventListener("click", () => {
      const on = rb.getAttribute("aria-pressed") !== "true";
      rb.setAttribute("aria-pressed", String(on));
      map.setLayoutProperty("rivers", "visibility", on ? "visible" : "none");
    });
    groups.get("Water").push(rb);
  }
  if (state.have["tiles/treecover2000.pmtiles"]) {
    const tb = railItem("Tree cover 2000 (\u226530 %)", "#316844", "");
    tb.addEventListener("click", () => {
      const on = tb.getAttribute("aria-pressed") !== "true";
      tb.setAttribute("aria-pressed", String(on));
      setVisibility(map, "treecover", on ? "visible" : "none");
    });
    groups.get("Land").push(tb);
  }
  const lakeBtn = railItem("Lake level", HUE, state.have["series/lake_level.json"] ? "" : "not available");
  lakeBtn.id = "lakeItem";
  lakeBtn.addEventListener("click", () => toggleLake());
  groups.get("Water").push(lakeBtn);

  for (const o of OVERLAYS) {
    if (o.railHidden) continue;
    const ok = o.hasEpochs ? Boolean(state.registry.forest_loss?.epochs)
             : o.type === "thematic" ? Boolean(state.registry[o.regKey]?.years || state.registry[o.regKey]?.classes)
             : state.have[o.file];
    const meta = ok ? "" : o.type === "climate" ? "preparing data" : "not built";
    const item = railItem(o.title, o.swatch || (o.legend ? o.legend.steps[Math.floor(o.legend.steps.length / 2)] : "#999"), meta);
    if (!ok) item.classList.add("unavailable");
    else item.addEventListener("click", () => setOverlay(state.overlay === o.id ? null : o.id));
    item.dataset.overlay = o.id;
    groups.get(o.group).push(item);
  }

  for (const [name, items] of groups) {
    if (!items.length) continue;
    const g = el("div", "group");
    const gl = el("div", "group-label", name);
    if (name === "Flood hazard" && state.registry.flood_hazard?.placeholder) {
      gl.append(" ", el("span", "pill restricted", "placeholder"));
    }
    g.append(gl);
    items.forEach((i) => g.append(i));
    rail.append(g);
  }
}

function railItem(title, swatchColor, meta) {
  const b = el("button", "item");
  b.setAttribute("aria-pressed", "false");
  const sw = el("span", "swatch");
  sw.style.background = swatchColor;
  b.append(sw, el("span", "label", title));
  if (meta) {
    const tag = el("span", "pill", meta);
    tag.style.marginLeft = "auto";
    b.append(tag);
  } else {
    b.append(el("span", "meta", ""));
  }
  return b;
}

async function setOverlay(id) {
  if (id && compare.isOpen()) compare.close(false);   // choosing a layer ends a swipe comparison
  state.overlay = id;
  document.querySelectorAll(".rail .item[data-overlay]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.overlay === id));
  });
  const shownId = id === "flood_freq" ? floodVariant() : id;
  for (const o of OVERLAYS) {
    setVisibility(map, "ov-" + o.id, o.id === shownId ? "visible" : "none");
  }
  const def = OVERLAYS.find((x) => x.id === id);
  climate.deactivate();
  land.deactivate();
  thematic.deactivate();
  if (def?.type === "thematic") {
    renderLegend(null);
    await thematic.activate(id);
    updateAttrib();
  } else if (def?.type === "climate") {
    renderLegend(null);                      // climate.js owns the legend while active
    await climate.activate(id);
  } else if (def?.type === "land") {
    renderLegend(null);
    await land.activate(id);
  } else {
    renderLegend(id);
  }
  updateAttrib();
  $("#popover").hidden = true;
}

/* ---------------- legend + attribution ---------------- */
function renderLegend(id) {
  const box = $("#legend");
  /* the Flood frequency entry draws the legend of its active season variant, plus the switch */
  const o = OVERLAYS.find((x) => x.id === (id === "flood_freq" ? floodVariant() : id));
  if (!o || !o.legend) { box.hidden = true; updateAttrib(); return; }
  const reg = state.registry.flood_hazard || {};
  box.innerHTML = "";
  box.append(el("h3", null, o.legend.title));
  if (id === "flood_freq") {
    const seg = el("div", "seg");
    for (const [key, label] of [["all", "All"], ["mam", "MAM"], ["ond", "OND"]]) {
      const b = el("button", null, label);
      b.setAttribute("aria-pressed", String(state.floodSeason === key));
      const built = key === "all" || state.have[`tiles/flood_freq_${key}.pmtiles`];
      if (!built) b.disabled = true;
      else b.addEventListener("click", () => { state.floodSeason = key; setOverlay("flood_freq"); });
      seg.append(b);
    }
    box.append(seg);
  }
  const steps = el("div", "steps");
  o.legend.steps.forEach((c) => { const s = el("span"); s.style.background = c; steps.append(s); });
  box.append(steps);
  box.append(el("div", "axis", `<span>${o.legend.labels[0]}</span><span>${o.legend.labels[1]}</span>`));
  if (o.legend.note) box.append(el("p", "src", o.legend.note));
  box.append(el("p", "src", (reg.source || "Copernicus EMS GFM") + " · " + (reg.period || "2016–2025")));
  box.hidden = false;
  updateAttrib(reg.citation);
}

function updateAttrib() {
  const o = OVERLAYS.find((x) => x.id === state.overlay);
  const names = { precip: " · CHIRPS v3 (UCSB CHC)", temperature: " · CHIRTS-ERA5 (UCSB CHC)",
                  spi3: " · SPI-3 from CHIRPS v3", population: " · WorldPop 2020 (CC-BY)",
                  forest_loss: " · Hansen GFC (UMD)", landcover: " · Esri/IO LULC (CC-BY)",
                  fire: " · NASA FIRMS VIIRS", burned_area: " · MODIS MCD64A1",
                  worldcover: " · ESA WorldCover (CC-BY)" };
  const extra = !o ? "" : (names[o.id] || " · Copernicus EMS GFM");
  const ref = (state.placeNames ? " · © OpenStreetMap contributors" : "")
            + (state.admin ? " · geoBoundaries (Runfola et al. 2020)" : "");
  $("#attrib").textContent = "Copernicus GLO-30 · Sentinel-2" + extra + ref;
}

/* ---------------- reference labels: OSM place names + admin boundaries ----------------
   Label-only layers from the Protomaps basemap extract (schema v4): no roads, buildings or fills.
   White text on a dark halo reads over imagery and every thematic palette. Collision runs across
   all symbol layers; layers higher in the stack are placed first, so the story labels (added later,
   on top) win where they collide, then places by population rank. A transparent marker layer
   ("labels-start") lets layers added at runtime (fire points) slot in below the labels. */
const LABEL_TEXT = { "text-color": "#ffffff", "text-halo-color": "rgba(17,26,34,0.88)", "text-halo-width": 1.5 };
const PLACE_IDS = ["osm-natural", "osm-water-river", "osm-water", "osm-village", "osm-town", "osm-city", "osm-country"];
const ADMIN_IDS = ["adm2-line", "adm1-line", "adm2-hit", "adm1-hit", "adm2-label", "adm1-label"];

function referenceLayers(sources) {
  const L = [{ id: "labels-start", type: "background", paint: { "background-opacity": 0 } }];
  if (state.registry.admin_boundaries) {
    sources.adm1 = { type: "geojson", data: dataUrl("vectors/adm1.geojson") };
    sources.adm2 = { type: "geojson", data: dataUrl("vectors/adm2.geojson") };
    sources.admLabels = { type: "geojson", data: dataUrl("vectors/admin_labels.geojson") };
    const hidden = { visibility: "none" };
    L.push(
      { id: "adm2-hit", type: "fill", source: "adm2", minzoom: 8, layout: hidden, paint: { "fill-opacity": 0 } },
      { id: "adm1-hit", type: "fill", source: "adm1", layout: hidden, paint: { "fill-opacity": 0 } },
      { id: "adm2-line", type: "line", source: "adm2", minzoom: 8, layout: hidden,
        paint: { "line-color": "#c9ced2", "line-width": 0.6, "line-dasharray": [3, 2], "line-opacity": 0.8 } },
      { id: "adm1-line", type: "line", source: "adm1", layout: hidden,
        paint: { "line-color": "#dfe3e6", "line-width": ["interpolate", ["linear"], ["zoom"], 6, 0.7, 11, 1.4],
                 "line-opacity": 0.9 } },
      { id: "adm1-label", type: "symbol", source: "admLabels", minzoom: 7, maxzoom: 11,
        filter: ["==", ["get", "level"], "ADM1"],
        layout: { ...hidden, "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"],
                  "text-size": 11, "text-letter-spacing": 0.06, "text-transform": "uppercase", "text-padding": 4 },
        paint: { ...LABEL_TEXT, "text-color": "#e4e8eb", "text-halo-width": 1.3 } },
      { id: "adm2-label", type: "symbol", source: "admLabels", minzoom: 9.5,
        filter: ["==", ["get", "level"], "ADM2"],
        layout: { ...hidden, "text-field": ["get", "name"], "text-font": ["Noto Sans Italic"], "text-size": 11,
                  "text-padding": 4 },
        paint: { ...LABEL_TEXT, "text-color": "#e4e8eb", "text-halo-width": 1.3 } });
  }
  if (state.have["tiles/osm_basemap.pmtiles"]) {
    sources.osm = { type: "vector", url: pmUrl("tiles/osm_basemap.pmtiles"),
                    attribution: "© OpenStreetMap contributors" };
    const sym = (font, size) => ({ "text-field": ["get", "name"], "text-font": [font], "text-size": size,
                                   "text-padding": 3, "text-max-width": 8 });
    const rank = ["-", 0, ["coalesce", ["get", "population_rank"], 0]];   // bigger places placed first
    L.push(
      { id: "osm-natural", type: "symbol", source: "osm", "source-layer": "pois", minzoom: 8,
        filter: ["all", ["has", "name"], ["in", ["get", "kind"], ["literal", ["national_park", "nature_reserve", "protected_area", "forest"]]]],
        layout: sym("Noto Sans Italic", 11), paint: { ...LABEL_TEXT, "text-color": "#e6f0dc" } },
      { id: "osm-water-river", type: "symbol", source: "osm", "source-layer": "water", minzoom: 9,
        filter: ["all", ["has", "name"], ["in", ["get", "kind"], ["literal", ["river", "canal", "stream"]]]],
        layout: { ...sym("Noto Sans Italic", 11), "symbol-placement": "line", "symbol-spacing": 400 },
        paint: { ...LABEL_TEXT, "text-color": "#d6eef2" } },
      { id: "osm-water", type: "symbol", source: "osm", "source-layer": "water",
        filter: ["all", ["has", "name"], ["==", ["geometry-type"], "Point"],
                 ["in", ["get", "kind"], ["literal", ["lake", "water", "bay", "reservoir"]]]],
        layout: sym("Noto Sans Italic", ["interpolate", ["linear"], ["zoom"], 6, 12, 10, 14]),
        paint: { ...LABEL_TEXT, "text-color": "#d6eef2" } },
      { id: "osm-village", type: "symbol", source: "osm", "source-layer": "places", minzoom: 11,
        filter: ["all", ["has", "name"], ["==", ["get", "kind"], "locality"],
                 ["in", ["get", "kind_detail"], ["literal", ["village", "hamlet"]]]],
        layout: { ...sym("Noto Sans Regular", 11), "symbol-sort-key": rank }, paint: LABEL_TEXT },
      { id: "osm-town", type: "symbol", source: "osm", "source-layer": "places", minzoom: 7,
        filter: ["all", ["has", "name"], ["==", ["get", "kind"], "locality"], ["==", ["get", "kind_detail"], "town"]],
        layout: { ...sym("Noto Sans Medium", ["interpolate", ["linear"], ["zoom"], 7, 11, 12, 13]), "symbol-sort-key": rank },
        paint: LABEL_TEXT },
      { id: "osm-city", type: "symbol", source: "osm", "source-layer": "places",
        filter: ["all", ["has", "name"], ["==", ["get", "kind"], "locality"], ["==", ["get", "kind_detail"], "city"]],
        layout: { ...sym("Noto Sans Medium", ["interpolate", ["linear"], ["zoom"], 6, 12, 12, 15]), "symbol-sort-key": rank },
        paint: LABEL_TEXT },
      { id: "osm-country", type: "symbol", source: "osm", "source-layer": "places", maxzoom: 8,
        filter: ["all", ["has", "name"], ["==", ["get", "kind"], "country"]],
        layout: { ...sym("Noto Sans Medium", 13), "text-transform": "uppercase", "text-letter-spacing": 0.12 },
        paint: { ...LABEL_TEXT, "text-color": "#f3f5f6" } });
  }
  return L;
}

/* admin unit under a map point, for the popover and the climate/land panel titles */
function adminAt(lngLat) {
  if (!map || !map.getLayer("adm1-hit") || map.getLayoutProperty("adm1-hit", "visibility") !== "visible") return null;
  const pt = map.project([lngLat.lng, lngLat.lat]);
  const hits = map.queryRenderedFeatures(pt, { layers: ["adm2-hit", "adm1-hit"] });
  const a1 = hits.find((f) => f.layer.id === "adm1-hit"), a2 = hits.find((f) => f.layer.id === "adm2-hit");
  if (!a1 && !a2) return null;
  const p = (a2 || a1).properties;
  return { adm1: a1?.properties.name, adm2: a2?.properties.name, country: p.country, iso: p.iso };
}
/* each country's own words for its ADM1 / ADM2 units (geoBoundaries boundaryCanonical, filled where "Unknown") */
const ADM_UNITS = { KEN: ["County", "Sub-county"], UGA: ["Region", "County"], TZA: ["Region", "District"],
                    RWA: ["Province", "District"], BDI: ["Province", "Commune"] };

/* ---------------- map ---------------- */
let map;
function initMap() {
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocol.tile);

  /* the basin outline and mask (ICPAC boundary) are not published: when the files are absent the two sources
     stay empty, so nothing is requested, while the "basin-line" and "dim" layers remain as anchors that
     climate.js (insert before "dim") and compare.js rely on */
  const EMPTY = { type: "FeatureCollection", features: [] };
  const optional = (f) => (state.have[f] ? dataUrl(f) : EMPTY);
  const sources = {
    basin: { type: "geojson", data: optional("vectors/basin.geojson") },
    mask: { type: "geojson", data: optional("vectors/basin_mask.geojson") },
    lake: { type: "geojson", data: dataUrl("vectors/lake.geojson") },
  };
  if (state.have["vectors/lake_detailed.geojson"]) {
    sources.lakeDetail = { type: "geojson", data: dataUrl("vectors/lake_detailed.geojson") };
  }
  const layers = [
    { id: "bg", type: "background", paint: { "background-color": "#dfe5ea" } },
  ];

  if (state.have["tiles/s2_rgb.pmtiles"]) {
    sources.s2 = { type: "raster", url: pmUrl("tiles/s2_rgb.pmtiles"), tileSize: 256 };
    layers.push({ id: "s2", type: "raster", source: "s2", paint: { "raster-resampling": "linear" } });
  }
  if (state.have["tiles/terrain.pmtiles"]) {
    sources.dem = { type: "raster-dem", url: pmUrl("tiles/terrain.pmtiles"),
                    tileSize: 256, encoding: "mapbox" };
    layers.push({ id: "hillshade", type: "hillshade", source: "dem",
                  paint: { "hillshade-exaggeration": 0.35, "hillshade-shadow-color": "#3c4148",
                           "hillshade-highlight-color": "#ffffff", "hillshade-accent-color": "#5b6672" } });
  }
  // uniform water fill from the native-resolution shoreline (islands as holes); hides mosaic stripes
  layers.push({ id: "lake-fill", type: "fill",
                source: state.have["vectors/lake_detailed.geojson"] ? "lakeDetail" : "lake",
                paint: { "fill-color": "#2e4b59", "fill-opacity": 1 } });
  layers.push({ id: "dim", type: "fill", source: "mask", paint: { "fill-color": "#1c232b", "fill-opacity": 0.28 } });

  for (const o of OVERLAYS) {
    if (o.hasEpochs || !state.have[o.file] || o.soon || !o.file.endsWith(".pmtiles")) continue;
    sources["src-" + o.id] = { type: "raster", url: pmUrl(o.file), tileSize: 256 };
    layers.push({ id: "ov-" + o.id, type: "raster", source: "src-" + o.id,
                  layout: { visibility: "none" },
                  paint: { "raster-resampling": "nearest", "raster-opacity": 0.85 } });
  }

  const th = thematic.layersFor(state.registry, pmUrl);
  Object.assign(sources, th.sources);
  layers.push(...th.layers);
  for (const [y, f] of Object.entries(state.registry.forest_loss?.urls?.epochs || {})) {
    sources["loss-le-" + y] = { type: "raster", url: pmUrl(f), tileSize: 256 };
    layers.push({ id: "loss-le-" + y, type: "raster", source: "loss-le-" + y,
                  layout: { visibility: "none" },
                  paint: { "raster-resampling": "nearest", "raster-opacity": 0.9 } });
  }
  if (state.have["tiles/worldcover2021.pmtiles"]) {
    sources.worldcover = { type: "raster", url: pmUrl("tiles/worldcover2021.pmtiles"), tileSize: 256 };
    layers.push({ id: "worldcover", type: "raster", source: "worldcover",
                  layout: { visibility: "none" },
                  paint: { "raster-resampling": "nearest", "raster-opacity": 0.8 } });
  }
  if (state.have["tiles/treecover2000.pmtiles"]) {
    sources.treecover = { type: "raster", url: pmUrl("tiles/treecover2000.pmtiles"), tileSize: 256 };
    layers.push({ id: "treecover", type: "raster", source: "treecover",
                  layout: { visibility: "none" },
                  paint: { "raster-resampling": "nearest", "raster-opacity": 0.8 } });
  }
  if (state.have["vectors/rivers.geojson"]) {
    sources.rivers = { type: "geojson", data: dataUrl("vectors/rivers.geojson") };
    layers.push({ id: "rivers", type: "line", source: "rivers",
                  layout: { visibility: "visible", "line-cap": "round", "line-join": "round" },
                  paint: { "line-color": "#117A8D", "line-opacity": 0.65,
                           "line-width": ["interpolate", ["linear"], ["get", "order"], 4, 0.5, 6, 1.3, 8, 2.4] } });
  }
  layers.push({ id: "basin-line", type: "line", source: "basin",
                paint: { "line-color": "#0a0a0a", "line-width": 1.4 } });
  layers.push({ id: "lake-hit", type: "fill", source: "lake", paint: { "fill-opacity": 0 } });  // click target only
  layers.push(...referenceLayers(sources));


  map = new maplibregl.Map({
    container: "map",
    style: { version: 8, ...splitLazy(sources, layers),   // PMTiles overlays added when first shown (layers.js)
             sky: { "sky-color": "#c8d4de", "horizon-color": "#e7ebef", "fog-color": "#e7ebef",
                    "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.7 },
             // fonts hosted with the app (Noto Sans from protomaps/basemaps-assets); built by string, not
             // new URL(), which would percent-encode the {fontstack}/{range} template braces
             glyphs: new URL(dataUrl("fonts/"), location.href).href + "{fontstack}/{range}.pbf" },
    center: [32.6, -1.15], zoom: 6.65, pitch: 38, bearing: -8,
    maxPitch: 62, minZoom: 6.15, maxZoom: 13, attributionControl: false,
    maxBounds: [[28.6, -4.75], [36.5, 2.0]],   // terrain tiles are padded 250 km beyond the DEM
  });
  window.__map = map;   // debug/probe handle
  window.fmtCoord = (lat, lng) => {
    const a = adminAt({ lat, lng });
    return fmtCoord(lat, lng) + (a ? ` · ${a.adm2 || a.adm1}, ${a.country}` : "");
  };
  window.closeFloatingPanels = closeFloating;
  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");

  map.on("load", async () => {
    const safe = async (name, fn) => { try { await fn(); } catch (e) { notice(`${name} layers failed to start: ${e.message}`); } };
    if (state.have["climate/app/app_meta.json"]) await safe("Climate", () => climate.init(map));
    await safe("Land", () => land.init(map, state.registry));
    await safe("Thematic", () => thematic.init(map));
    applyHash();
    if (map.setSky) {
      map.setSky({ "sky-color": "#c8d4de", "horizon-color": "#e7ebef", "fog-color": "#e7ebef",
                   "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.7 });
    }
    if (state.have["tiles/terrain.pmtiles"]) {
      map.setTerrain({ source: "dem", exaggeration: 1.8 });
    } else {
      $("#exag").disabled = true;
    }
  });

  map.on("click", "lake-hit", (e) => { toggleLake(true); e.preventDefault?.(); });
  map.on("click", (e) => {
    if (map.queryRenderedFeatures(e.point, { layers: ["lake-hit"] }).length) return;
    if (climate.isActive()) { climate.showCell(e.lngLat); return; }
    if (land.isActive()) { land.onClick(e.lngLat); return; }
    if (thematic.isActive()) { thematic.onClick(e.lngLat); return; }
    showPopover(e);
  });
  map.on("mouseenter", "lake-hit", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "lake-hit", () => (map.getCanvas().style.cursor = ""));
}

/* shareable state: #layer=precip&var=tmean&season=ond&mode=anomaly&year=2020&cell=34.5,-0.2 */
async function applyHash() {
  const h = new URLSearchParams(location.hash.slice(1));
  const c = h.get("c");
  if (c) {
    const [lng, lat, zoom, pitch] = c.split(",").map(Number);
    map.jumpTo({ center: [lng, lat], zoom: zoom || 10, pitch: pitch ?? 0, bearing: 0 });
  }
  if (h.get("lake")) toggleLake(true);
  if (!h.get("layer")) return;
  const id = h.get("layer");
  climate.presetFromHash(h);
  const item = document.querySelector(`.rail .item[data-overlay="${id}"]`);
  if (item && !item.classList.contains("unavailable")) await setOverlay(id);
  const cell = h.get("cell");
  if (cell && climate.isActive()) {
    const [lng, lat] = cell.split(",").map(Number);
    await climate.showCell({ lng, lat });
  }
}

/* WGS84 -> UTM zone 36 South (EPSG:32736), for reading the flood query COG */
function toUTM36S(lat, lng) {
  const a = 6378137, f = 1 / 298.257223563, k0 = 0.9996, e2 = f * (2 - f), ep2 = e2 / (1 - e2);
  const phi = lat * Math.PI / 180, lam = lng * Math.PI / 180, lam0 = 33 * Math.PI / 180;
  const N = a / Math.sqrt(1 - e2 * Math.sin(phi) ** 2), T = Math.tan(phi) ** 2;
  const C = ep2 * Math.cos(phi) ** 2, A = Math.cos(phi) * (lam - lam0);
  const M = a * ((1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256) * phi
    - (3 * e2 / 8 + 3 * e2 ** 2 / 32 + 45 * e2 ** 3 / 1024) * Math.sin(2 * phi)
    + (15 * e2 ** 2 / 256 + 45 * e2 ** 3 / 1024) * Math.sin(4 * phi)
    - (35 * e2 ** 3 / 3072) * Math.sin(6 * phi));
  const x = 500000 + k0 * N * (A + (1 - T + C) * A ** 3 / 6 + (5 - 18 * T + T ** 2 + 72 * C - 58 * ep2) * A ** 5 / 120);
  const y = 10000000 + k0 * (M + N * Math.tan(phi) * (A ** 2 / 2 + (5 - T + 9 * C + 4 * C ** 2) * A ** 4 / 24
    + (61 - 58 * T + T ** 2 + 600 * C - 330 * ep2) * A ** 6 / 720));
  return [x, y];
}

let floodImg = null;
async function floodValuesAt(lngLat) {
  if (!floodImg) {
    const tif = await GeoTIFF.fromUrl(dataUrl("query/flood_query_100m.tif"), { allowFullFile: false });
    floodImg = await tif.getImage();
  }
  const [x, y] = toUTM36S(lngLat.lat, lngLat.lng);
  const [ox, oy] = floodImg.getOrigin(), [rx, ry] = floodImg.getResolution();
  const col = Math.floor((x - ox) / rx), row = Math.floor((y - oy) / ry);
  if (col < 0 || row < 0 || col >= floodImg.getWidth() || row >= floodImg.getHeight()) return null;
  const d = await floodImg.readRasters({ window: [col, row, col + 1, row + 1] });
  return { years: d[0][0], freq: d[1][0], excl: d[2][0] };
}

async function showPopover(e) {
  const p = $("#popover");
  /* terrain elevation deliberately not shown: GLO-30 (2011-2015 epoch, resampled) and DAHITI WSE
     differ by 1-2 m on the lake and confuse more than they inform */
  const rows = [
    `<div class="row"><span>Place</span><span>${fmtCoord(e.lngLat.lat, e.lngLat.lng)}</span></div>`,
  ];
  const adm = adminAt(e.lngLat);
  if (adm) {
    const [u1, u2] = ADM_UNITS[adm.iso] || ["Admin 1", "Admin 2"];
    if (adm.adm2) rows.push(`<div class="row"><span>${u2}</span><span>${adm.adm2}</span></div>`);
    if (adm.adm1) rows.push(`<div class="row"><span>${u1}</span><span>${adm.adm1}</span></div>`);
    rows.push(`<div class="row"><span>Country</span><span>${adm.country}</span></div>`);
  }
  closeFloating("popover");
  const o = OVERLAYS.find((x) => x.id === state.overlay);
  if (o && o.group === "Flood hazard") {
    const v = await floodValuesAt(e.lngLat).catch(() => null);
    if (v && v.excl === 254) {           // look-alike zone (band 3 code 254, DATA_REPORT 3.1)
      rows.push(`<p class="meta">Not assessed: repeated radar detections over dry grassland with no support in the `
                + `optical record (JRC GSW); likely radar look-alikes, not flooding. See DATA_REPORT §3.1.</p>`);
    } else if (!v || v.years === 255) {
      rows.push(`<div class="row"><span>Flood record</span><span>no data (water or outside basin)</span></div>`);
    } else {
      rows.push(`<div class="row"><span>Years flooded</span><span>up to ${v.years} of 10</span></div>`,
                `<div class="row"><span>Flood frequency</span><span>${v.freq === 255
                  ? "not computed" : "up to " + v.freq + " % of valid obs."}</span></div>`);
      if (v.excl !== 255 && v.excl >= 50) {
        rows.push(`<div class="row"><span>Observations excluded</span><span>up to ${v.excl} %</span></div>`,
                  `<p class="meta">Radar sensitivity low here; absence of floods is uncertain.</p>`);
      }
    }
    rows.push(`<p class="meta">Flooded in up to N of 10 years within 100 m (maximum of the 20 m cells). `
              + `Hazard proxy, not risk.</p>`);
  }
  p.innerHTML = `<h3>${o ? o.title : "Terrain"}</h3>${rows.join("")}
    <p class="meta">${o ? "Copernicus EMS GFM · 2016–2025" : "Copernicus GLO-30"}</p>`;
  const r = $("#map").getBoundingClientRect();
  p.style.left = Math.min(e.point.x + 12, r.width - 300) + "px";
  p.style.top = Math.min(e.point.y + 12, r.height - 140) + "px";
  p.hidden = false;
}

/* ---------------- lake panel: KPIs + hydrograph (the signature element) ---------------- */
let lakeLoaded = false;
async function toggleLake(open) {
  const panel = $("#lakePanel");
  const show = open === true ? true : panel.hidden;
  if (show) closeFloating("lakePanel");
  panel.hidden = !show;
  $("#lakeItem").setAttribute("aria-pressed", String(show));
  if (!show || lakeLoaded) return;
  lakeLoaded = true;
  const body = $("#lakeBody");

  if (!state.have["series/lake_level.json"]) {
    body.append(el("div", "empty", "Lake-level series not available in this version."));
    console.info("lake level: series/lake_level.json missing; run prep/05_prefetch_dahiti.py (needs DAHITI_API_KEY) and reload.");
    return;
  }
  const s = await getJSON(dataUrl("series/lake_level.json"));
  const pts = s.data;
  const wse = pts.map((p) => p.wse);
  const latest = pts[pts.length - 1];
  const sorted = [...wse].sort((a, b) => a - b);
  const median = sorted[Math.floor(sorted.length / 2)];
  const maxI = wse.indexOf(Math.max(...wse));
  const rec = pts[maxI];

  const d = (v) => v.toFixed(2);
  const kpis = el("div", "kpis");
  kpis.append(
    el("div", "lead", `<div class="label">Latest level · ${latest.date}</div>
       <div class="value num">${d(latest.wse)} <span class="unit">m</span></div>`),
    el("div", null, `<div class="label">vs median</div>
       <div class="value num">${latest.wse >= median ? "+" : ""}${d(latest.wse - median)} <span class="unit">m</span></div>`),
    el("div", null, `<div class="label">Record · ${rec.date.slice(0, 7)}</div>
       <div class="value num">${d(rec.wse)} <span class="unit">m</span></div>`),
  );
  body.append(kpis);

  /* monthly means for the chart */
  const byMonth = new Map();
  for (const p of pts) {
    const k = p.date.slice(0, 7);
    const m = byMonth.get(k) || { s: 0, n: 0 };
    m.s += p.wse; m.n++; byMonth.set(k, m);
  }
  const keys = [...byMonth.keys()].sort();
  const values = keys.map((k) => +(byMonth.get(k).s / byMonth.get(k).n).toFixed(2));
  const labels = keys.map((k) => (k.endsWith("-01") && +k.slice(0, 4) % 5 === 0 ? k.slice(0, 4) : ""));
  const recK = rec.date.slice(0, 7);

  const block = el("div", "chart-block");
  block.append(el("h3", null, "Water surface elevation, monthly mean (m)"));
  const mount = el("div");
  block.append(mount);
  Charts.line(mount, {
    labels, series: [{ name: "WSE", values }],
    format: (v) => v.toFixed(1), height: 190,
    min: Math.floor(Math.min(...values)) - 0.3, max: Math.ceil(Math.max(...values)) + 0.3,
    annotations: [{ at: keys.indexOf(recK), label: `Record ${rec.wse.toFixed(1)} m`, short: "record" }],
    reference: { value: median, label: "median" },
  });
  block.append(el("p", "meta",
    `${s.n.toLocaleString()} altimetry passes, ${pts[0].date} → ${latest.date} · ${s.source} · fetched ${s.fetched}. ` +
    "WSE is geoid-referenced altimetry of today’s lake; it is not comparable with the GLO-30 terrain, whose surface dates from 2011–2015."));
  body.append(block);
}

/* ---------------- about panel ---------------- */
function buildAbout() {
  const body = $("#aboutBody");
  const brand = el("div", "about-brand", `
    <img src="assets/brand/cgiar-mfl-lockup.png" alt="CGIAR Multifunctional Landscapes" width="180" height="60">
    <p>Part of <a href="https://mosaic-mfl.github.io/website/">MOSAIC</a> — the CGIAR Multifunctional
       Landscapes Science Programme. See the <a href="https://mosaic-mfl.github.io/website/catalogue">data
       catalogue</a> and the <a href="../DATA_REPORT.md">full data report</a> for this app.</p>
    <p class="meta">Content licensed under CC BY 4.0 unless otherwise stated. Each layer below carries its
       own source, period and citation.</p>`);
  body.append(brand);
  const layers = Object.values(state.registry);
  if (!layers.length) {
    body.append(el("div", "empty", "Layer registry not found (data/meta/layers.json)."));
    return;
  }
  for (const l of layers) {
    const sec = el("div", "chart-block");
    const h = el("h3", null, l.title);
    if (l.placeholder) h.append(" ", el("span", "pill restricted", "placeholder"));
    sec.append(h);
    sec.append(el("p", "meta",
      [l.source, l.period, l.units, l.licence].filter(Boolean).join(" · ")));
    if (l.citation) sec.append(el("p", "meta", l.citation));
    if (l.attribution) sec.append(el("p", "meta", l.attribution));
    if (l.caveats) sec.append(el("p", "meta", l.caveats));
    body.append(sec);
  }
}

/* ---------------- ui wiring ---------------- */
function wireUI() {
  $("#exag").addEventListener("input", (e) => {
    const v = +e.target.value;
    $("#exagVal").textContent = "×" + v.toFixed(1);
    if (map.getTerrain()) map.setTerrain({ source: "dem", exaggeration: v });
  });
  $("#lakeClose").addEventListener("click", () => toggleLake());
  $("#aboutBtn").addEventListener("click", () => {
    const show = $("#aboutPanel").hidden;
    if (show) closeFloating("aboutPanel");
    $("#aboutPanel").hidden = !show;
  });
  $("#aboutClose").addEventListener("click", () => ($("#aboutPanel").hidden = true));
  /* narrow windows: the layer menu is a drawer. ☰ turns into ✕ while it is open; it also closes on Escape,
     on a tap on the map, and on a phone after a layer is chosen (so the layer can be seen) */
  const setMenu = (open) => {
    $("#sidebar").classList.toggle("open", open);
    $("#menuBtn").setAttribute("aria-expanded", String(open));
    $("#menuBtn").setAttribute("aria-label", open ? "Close menu" : "Menu");
    $("#menuBtn path").setAttribute("d", open ? "M3 3l10 10M13 3L3 13" : "M2 4h12M2 8h12M2 12h12");
  };
  $("#menuBtn").addEventListener("click", () => setMenu(!$("#sidebar").classList.contains("open")));
  map.on("click", () => setMenu(false));
  $("#rail").addEventListener("click", (e) => {
    if (e.target.closest(".item") && matchMedia("(max-width: 480px)").matches) setMenu(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      setMenu(false);
      for (const id of ["popover", "lakePanel", "aboutPanel", "storiesPanel"]) $("#" + id).hidden = true;
      $("#storiesBtn").setAttribute("aria-expanded", "false");
    }
  });
}
