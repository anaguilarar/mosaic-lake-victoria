/* Uses & studies drawer: two tabs.
   "Story" (default) - scroll-driven chapters from data/meta/story.json. A chapter entering the middle
   of the drawer applies its map state (layer, climate time step, camera). Charts render inline from
   the app's served series; static figures (prep/90_story_figures.py) enlarge over the map on click.
   Rules carried in the registry: study numbers as printed (page recorded), app numbers labelled
   "this app's analysis", pending chapters show a placeholder.
   "Studies" - the question cards (stories.json): published findings verified against the PDFs in
   bibliography/, or explore questions. "Show me on the map" applies the card's state and closes the
   drawer; the Story tab keeps the drawer open and repositions the legend and time bar instead. */

import * as compare from "./compare.js";

import { dataUrl } from "./config.js";
const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

const state = { stories: [], chapters: [], storyTitle: "", hooks: null, expanded: null,
                tab: "story", series: new Map(), io: null, chapter: null };

/* app.js hands over: { setOverlay, toggleLake, map, overlayAvailable(id), overlayTitle(id),
                        activeOverlay(), presetClimate(params) } */
export async function init(hooks) {
  state.hooks = hooks;
  $("#storiesBtn").addEventListener("click", toggle);
  $("#storiesClose").addEventListener("click", () => setOpen(false));
  const grab = async (f) => { try { const r = await fetch(dataUrl("meta/" + f)); return r.ok ? r.json() : null; } catch { return null; } };
  const [cards, story] = await Promise.all([grab("stories.json"), grab("story.json")]);
  state.stories = cards?.stories || [];
  state.chapters = story?.chapters || [];
  state.storyTitle = story?.title || "Story";
}

export function isOpen() { return !$("#storiesPanel").hidden; }
export function toggle() { setOpen($("#storiesPanel").hidden); }

function setOpen(open) {
  const panel = $("#storiesPanel");
  if (open) { window.closeFloatingPanels?.("storiesPanel"); render(); }
  panel.hidden = !open;
  $("#storiesBtn").setAttribute("aria-expanded", String(open));
  syncBodyClass();
}

function syncBodyClass() {
  const on = isOpen() && state.tab === "story";
  const was = document.body.classList.contains("story-open");
  document.body.classList.toggle("story-open", on);
  if (on !== was) setStoryMode(on);
  if (!on && compare.isOpen()) compare.close(true);
}

/* story mode: place labels (and the Nyando highlight) on the map; camera padding keeps the subject
   left of the drawer. Leaving story mode hides them and eases the padding back. */
function setStoryMode(on) {
  const map = state.hooks?.map;
  if (!map) return;
  const apply = () => {
    ensureStoryLayers(map);
    map.setLayoutProperty("story-labels", "visibility", on ? "visible" : "none");
    map.setLayoutProperty("story-label-nyando", "visibility", on ? "visible" : "none");
    if (!on) for (const id of ["nyando-hl", "sediment-line", "sediment-label"]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", "none");
    }
    if (!on) map.easeTo({ padding: { top: 0, bottom: 0, left: 0, right: 0 }, duration: 400, freezeElevation: true });
  };
  if (map.isStyleLoaded()) apply(); else map.once("load", apply);
}

function ensureStoryLayers(map) {
  if (map.getSource("story-labels")) return;
  map.addSource("story-labels", { type: "geojson", data: dataUrl("vectors/story_labels.geojson") });
  map.addSource("nyando", { type: "geojson", data: dataUrl("vectors/nyando_river.geojson") });
  /* chapter 8: Humphrey et al. (2025) sediment sub-catchments, approximate, derived from HydroSHEDS
     (analysis/flood_frequency/scripts/23_sediment_subcatchments.py) */
  map.addSource("sediment", { type: "geojson", data: dataUrl("vectors/sediment_subcatchments.geojson") });
  map.addSource("sedimentLabels", { type: "geojson", data: dataUrl("vectors/sediment_subcatchments_labels.geojson") });
  map.addLayer({ id: "sediment-line", type: "line", source: "sediment", layout: { visibility: "none" },
    paint: { "line-color": "#ffffff", "line-width": 2, "line-opacity": 0.9 } });
  map.addLayer({ id: "sediment-label", type: "symbol", source: "sedimentLabels", layout: { visibility: "none",
      "text-field": ["get", "name"], "text-font": ["Noto Sans Medium"], "text-size": 13, "text-max-width": 9 },
    paint: { "text-color": "#ffffff", "text-halo-color": "rgba(17,26,34,0.9)", "text-halo-width": 1.6 } });
  map.addLayer({ id: "nyando-hl", type: "line", source: "nyando",
    layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#C97D1B", "line-opacity": 0.95,
             "line-width": ["interpolate", ["linear"], ["get", "order"], 4, 1.8, 6, 3.2, 8, 5 ] } });
  map.addLayer({ id: "story-labels", type: "symbol", source: "story-labels",
    filter: ["!=", ["get", "name"], "Nyando River"],
    layout: { visibility: "none", "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"],
              "text-size": 13, "text-padding": 6 },
    paint: { "text-color": "#1C2B3A", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
  /* the Nyando label gets its own layer: right-anchored at an upstream point, so the text runs back
     along the river and stays inside the drawer-padded viewport (text-anchor is not data-driven) */
  /* minzoom: at basin-wide zoom the anchor point projects under the drawer (and further west would
     collide with 'Kano plains'), so the river label only renders at the zoomed-in chapters */
  map.addLayer({ id: "story-label-nyando", type: "symbol", source: "story-labels", minzoom: 7.4,
    filter: ["==", ["get", "name"], "Nyando River"],
    layout: { visibility: "none", "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"],
              "text-size": 13, "text-anchor": "right", "text-offset": [-0.3, 0] },
    paint: { "text-color": "#1C2B3A", "text-halo-color": "#ffffff", "text-halo-width": 1.6 } });
}

/* camera padding so the chapter's subject sits centred in the visible map, not under the drawer/sheet */
function storyPadding() {
  const map = state.hooks.map;
  return window.matchMedia("(max-width: 900px)").matches
    ? { top: 0, left: 0, right: 0, bottom: Math.round(map.getContainer().clientHeight * 0.5) }
    : { top: 0, left: 0, bottom: 0, right: 424 };
}

function setHeader(i) {
  const story = state.tab === "story";
  $("#storiesH2").textContent = story ? state.storyTitle : "Uses & studies";
  $("#storiesMeta").textContent = story
    ? `Chapter ${i} / ${state.chapters.length} · the map follows the scroll`
    : "Questions this app helps answer, with published findings where they exist";
}

/* ---------------- shell: tabs ---------------- */
function render() {
  const body = $("#storiesBody");
  body.innerHTML = "";
  state.io?.disconnect(); state.io = null;
  const tabs = el("div", "seg story-tabs");
  for (const [id, label] of [["story", "Story"], ["studies", "Studies"]]) {
    const b = el("button", null, label);
    b.setAttribute("aria-pressed", String(state.tab === id));
    b.addEventListener("click", () => { state.tab = id; render(); syncBodyClass(); });
    tabs.append(b);
  }
  body.append(tabs);
  if (state.tab === "story") renderStory(body); else renderStudies(body);
  syncBodyClass();
}

/* ---------------- story tab ---------------- */
function renderStory(body) {
  if (!state.chapters.length) {
    body.append(el("div", "empty", "No story registered yet (data/meta/story.json)."));
    return;
  }
  setHeader(1);
  for (const ch of state.chapters) body.append(chapterEl(ch));
  body.append(el("p", "stories-note",
    "Study numbers are as printed in the cited papers (pages in story.json); " +
    "“this app's analysis” numbers come from the app's own data (methods in the data report)."));
  body.append(el("div", "story-spacer"));   // lets the last chapter reach the trigger band

  state.io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (en.isIntersecting && en.target.dataset.id !== state.chapter) {
        state.chapter = en.target.dataset.id;
        body.querySelectorAll(".chapter").forEach((c) => c.classList.toggle("active", c === en.target));
        setHeader(state.chapters.findIndex((c) => c.id === state.chapter) + 1);
        /* IO callbacks run inside the browser's rendering steps, i.e. inside maplibre's own animation
           frame: a flyTo here re-enters the camera's running task queue. Defer to a macrotask. */
        const id = state.chapter;
        setTimeout(() => { if (state.chapter === id) applyChapter(state.chapters.find((c) => c.id === id)); }, 0);
      }
    }
  }, { root: body, rootMargin: "-30% 0px -62% 0px", threshold: 0 });   // a thin band near the top third
  body.querySelectorAll(".chapter").forEach((c) => state.io.observe(c));
  /* the first chapter is the opening state, before any scroll */
  state.chapter = state.chapters[0].id;
  body.querySelector(".chapter")?.classList.add("active");
  setTimeout(() => { if (state.chapter === state.chapters[0].id) applyChapter(state.chapters[0]); }, 0);
}

function chapterEl(ch) {
  const c = el("section", "chapter");
  c.dataset.id = ch.id;
  const h = el("h3", "chapter-title", ch.title);
  if (ch.status === "pending") h.append(" ", el("span", "pill review", "pending"));
  if (ch.status === "provisional") h.append(" ", el("span", "pill review", "provisional"));
  c.append(h);
  c.append(el("p", "chapter-text", ch.text));
  if (ch.status === "pending" && ch.placeholder) c.append(el("div", "story-placeholder", ch.placeholder));
  if (ch.visual?.figure && ch.status !== "pending") {
    const img = el("img", "chapter-figure");
    img.src = dataUrl(ch.visual.figure); img.alt = ch.visual.alt || ch.title; img.loading = "lazy";
    img.title = "Click to enlarge";
    img.addEventListener("click", () => enlarge(img.src, img.alt));
    c.append(img);
  }
  if (ch.visual?.chart && ch.status !== "pending") {
    const mount = el("div", "chapter-chart");
    c.append(mount);
    buildChart(ch.visual.chart, mount).catch(() => mount.append(el("div", "empty", "Chart data not available.")));
  }
  if (ch.visual?.steps?.length && ch.status !== "pending") {
    const row = el("div", "story-actions");
    for (const st of ch.visual.steps) {
      const chip = el("button", "story-chip", st.label);
      chip.addEventListener("click", () => fly(st.camera));
      row.append(chip);
    }
    c.append(row);
  }
  if (ch.visual?.note) c.append(el("p", "stories-note", ch.visual.note));
  if (ch.visual?.pending_note) c.append(el("p", "stories-note", ch.visual.pending_note));
  if (ch.visual?.exposure && ch.status !== "pending") {
    const mount = el("div", "story-exposure");
    c.append(mount);
    exposureCounter(ch.visual.exposure, mount).catch(() => { mount.replaceChildren(el("div", "empty", "Exposure data not available.")); });
  }
  for (const n of ch.numbers || []) c.append(numberEl(n));
  if (ch.sources?.length) {
    const d = el("details", "sources");
    d.append(el("summary", null, "Sources"));
    for (const s of ch.sources) d.append(el("p", null, s));
    c.append(d);
  }
  if (ch.visual?.action === "explore") {
    const btn = el("button", "story-show", "Open the explorer at this view");
    btn.addEventListener("click", async () => { await applyChapter(ch); setOpen(false); });
    c.append(el("div", "story-actions"), btn);
  }
  return c;
}

/* chapter 5: people in cells where water was detected in >= N years (series/flood_exposure.json, prep/13_exposure.py),
   with N and the area chosen by the reader; label and note come from story.json */
async function exposureCounter(cfg, mount) {
  const s = await series("flood_exposure.json");
  const regions = Object.keys(s.regions);
  const short = (r) => (r === "Lake Victoria Basin" ? "Whole basin" : r);
  let region = regions[0], N = cfg.default_n || 1;
  const pick = (vals, cur, fmt, on) => {
    const g = el("div", "seg");
    for (const v of vals) {
      const b = el("button", null, fmt(v));
      b.setAttribute("aria-pressed", String(v === cur));
      b.addEventListener("click", () => { g.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); on(v); });
      g.append(b);
    }
    return g;
  };
  const num = el("div");
  const draw = () => num.replaceChildren(numberEl({
    value: Number(s.regions[region][String(N)] ?? 0).toLocaleString("en-US"),
    label: `${short(region)}: ${cfg.label.replace("≥ N years", N === 1 ? "≥ 1 year" : `≥ ${N} years`)}`,
    source: { kind: "app", method: s.method } }));
  const controls = el("div", "story-actions");
  controls.append(pick(cfg.n_values || [1, 2, 3, 5], N, (v) => "≥ " + v + (v === 1 ? " year" : " years"), (v) => { N = v; draw(); }),
                  pick(regions, region, short, (v) => { region = v; draw(); }));
  mount.replaceChildren(controls, num);
  if (cfg.note) mount.append(el("p", "stories-note", cfg.note));
  draw();
}

function numberEl(n) {
  const d = el("div", "story-num");
  d.append(el("span", "story-num-val num", n.value));
  const right = el("div", "story-num-body", n.label);
  const src = n.source || {};
  if (src.kind === "study") {
    right.append(el("div", "meta", `${src.citation}${src.page ? " · " + src.page : ""}`));
  } else if (src.kind === "app") {
    const m = el("div", "meta", `this app's analysis — ${src.method} · `);
    const a = el("a", null, "data report"); a.href = "../DATA_REPORT.md"; a.target = "_blank"; a.rel = "noopener";
    m.append(a);
    right.append(m);
  }
  d.append(right);
  return d;
}

/* chapter applications are serialised: each takes a ticket, and one overtaken by a later scroll stops at
   its next await - otherwise a stale apply can close the comparison while the current one reopens it */
let applySeq = 0;
async function applyChapter(ch) {
  if (!ch) return;
  const ticket = ++applySeq;
  const stale = () => ticket !== applySeq;
  const h = state.hooks, v = ch.visual || {};
  if (v.time) {
    const p = new URLSearchParams();
    for (const [k, val] of Object.entries(v.time)) p.set(k, String(val));
    h.presetClimate(p);
  }
  const swipe = v.type === "swipe" && ch.status !== "pending" && h.overlayAvailable(v.right);
  if (!swipe && compare.isOpen()) compare.close(false);   // the next chapter's flyTo sets the pitch
  const layer = swipe ? null : (v.layers || []).find((id) => h.overlayAvailable(id));
  await h.setOverlay(layer || null);
  if (stale()) return;
  if (h.map.getLayer("nyando-hl")) {
    h.map.setLayoutProperty("nyando-hl", "visibility", v.highlight ? "visible" : "none");
    for (const id of ["sediment-line", "sediment-label"]) {
      h.map.setLayoutProperty(id, "visibility", v.subcatchments ? "visible" : "none");
    }
  }
  /* swipe: open first - its synchronous part levels the map (terrain off, max pitch 0) before the
     flight starts. Opening during a flight would stop the camera mid-way, still tilted. */
  const opening = swipe && !compare.isOpen() ? compare.open(h.map, {
      overlayLayerId: "ov-" + v.right, left: v.left_label, right: v.right_label, padding: storyPadding(),
      restorePitch: v.camera?.pitch ?? 0,          // Close keeps the chapter's own view, terrain back on
      /* Close keeps the chapter's subject on screen: the overlay goes back on the main map */
      onClose: () => { if (state.chapter === ch.id) h.setOverlay(v.right); },
    }) : null;
  if (v.camera) fly(v.camera);
  await opening;
}

/* freezeElevation: without it, maplibre 5.6's terrain elevation update can crash mid-flight
   ('reading wrap') and jam the camera's task queue for good */
function fly(cam) {
  state.hooks.map.flyTo({ center: [cam.lng, cam.lat], zoom: cam.zoom ?? 8, pitch: cam.pitch ?? 0, bearing: 0,
                          duration: 1600, freezeElevation: true, padding: storyPadding() });
}

/* figure overlay over the map */
function enlarge(src, alt) {
  let ov = $("#figOverlay");
  if (!ov) {
    ov = el("div", "fig-overlay"); ov.id = "figOverlay";
    ov.addEventListener("click", () => (ov.hidden = true));
    document.body.append(ov);
  }
  ov.innerHTML = "";
  const img = el("img"); img.src = src; img.alt = alt || "";
  ov.append(img, el("p", "meta", "Click anywhere to close"));
  ov.hidden = false;
}

/* ---------------- inline charts (data: the app's own series files) ---------------- */
async function series(file) {
  if (!state.series.has(file)) state.series.set(file, (await fetch(dataUrl("series/" + file))).json());
  return state.series.get(file);
}
const yearLabels = (keys, step = 5) => keys.map((k) => (+String(k).slice(0, 4) % step === 0 && (String(k).length === 4 || String(k).endsWith("-01")) ? String(k).slice(0, 4) : ""));

async function buildChart(kind, mount) {
  /* Charts.line / Charts.bars own their element: they clear it and redraw (again once fonts load), so the
     heading and every chart get their own child - never draw into a container that holds anything else */
  const host = (title, parent = mount) => {
    if (title) parent.append(el("h4", "chapter-chart-title", title));
    const d = el("div"); parent.append(d); return d;
  };
  if (kind === "ond_totals") {
    const p = await series("precip_basin.json");
    const years = [...new Set(Object.keys(p.monthly).map((k) => k.slice(0, 4)))].sort();
    const ond = (y) => ["10", "11", "12"].reduce((a, m) => a + (p.monthly[`${y}-${m}`] ?? NaN), 0);
    const ys = years.filter((y) => Number.isFinite(ond(y)));
    const vals = ys.map((y) => Math.round(ond(y)));
    const norm = Math.round(ys.filter((y) => y >= "1991" && y <= "2020").reduce((a, y) => a + ond(y), 0) / 30);
    Charts.line(host("Short-rains (OND) basin rainfall, mm"), { labels: yearLabels(ys), series: [{ name: "OND", values: vals }],
      format: (v) => v + " mm", tickFormat: (v) => Math.round(v), height: 150,
      annotations: [{ at: ys.indexOf("2019"), label: "2019 · " + vals[ys.indexOf("2019")] + " mm", short: "2019" }],
      reference: { value: norm, label: "normal" } });
  } else if (kind === "lake_level") {
    const s = await series("lake_level.json");
    const byMonth = new Map();
    for (const pt of s.data) {
      const k = pt.date.slice(0, 7); const m = byMonth.get(k) || { s: 0, n: 0 };
      m.s += pt.wse; m.n++; byMonth.set(k, m);
    }
    const keys = [...byMonth.keys()].sort();
    const vals = keys.map((k) => +(byMonth.get(k).s / byMonth.get(k).n).toFixed(2));
    Charts.line(host("Lake level, monthly mean (m, DAHITI altimetry)"), { labels: yearLabels(keys), series: [{ name: "WSE", values: vals }],
      format: (v) => v.toFixed(2) + " m", tickFormat: (v) => Math.round(v), height: 160,
      min: Math.floor(Math.min(...vals)), max: Math.ceil(Math.max(...vals)),
      annotations: [{ from: keys.indexOf("2019-11"), to: keys.indexOf("2020-05"), label: "2020 rise" },
                    { at: keys.indexOf("2024-05"), label: "May 2024 record", short: "record" }] });
  } else if (kind === "spi3_series") {
    const s = await series("spi3_basin.json");
    const keys = Object.keys(s.monthly).sort();
    const vals = keys.map((k) => s.monthly[k]);
    Charts.line(host("Basin-mean SPI-3, monthly"), { labels: yearLabels(keys), series: [{ name: "SPI-3", values: vals }],
      format: (v) => v.toFixed(2), tickFormat: (v) => v, height: 150, min: -3, max: 3,
      yTicks: [-3, -2, -1, 0, 1, 2, 3],
      annotations: [{ from: keys.indexOf("2019-10"), to: keys.indexOf("2020-07"), label: "2020 floods" },
                    { at: keys.indexOf("2024-05"), label: "2024 floods", short: "2024" }],
      reference: { value: 0, label: "normal" } });
  } else if (kind === "forest_loss") {
    const f = await series("forest_loss.json");
    const reg = f.regions["Lake Victoria Basin"];
    const years = Object.keys(reg).sort();
    Charts.bars(host("Tree-cover loss in the basin (km²/year)"), { labels: years.map((y) => (+y % 5 === 0 ? y : "")), values: years.map((y) => reg[y]),
      height: 140, format: (v) => Math.round(v).toLocaleString() + " km²",
      highlight: years.indexOf("2017"),
      annotations: [{ from: years.indexOf("2011"), to: years.indexOf("2013"), label: "Landsat 8 improves detection" }] });
    /* small multiples: one mini chart per approved sub-basin, all on the same y-scale */
    const subs = ["Nzoia", "Yala", "Nyando", "Sondu-Miriu"].filter((n) => f.regions[n]);
    if (subs.length) {
      const top = Math.max(...subs.flatMap((n) => Object.values(f.regions[n])));
      mount.append(el("h4", "chapter-chart-title", "By sub-basin (km²/year, same scale)"));
      const grid = el("div", "mini-grid"); mount.append(grid);
      for (const n of subs) {
        const cell = el("div", "mini-cell");
        const tot = Object.values(f.regions[n]).reduce((a, v) => a + v, 0);
        cell.append(el("div", "mini-title", `${n} <span class="num">${Math.round(tot).toLocaleString()} km²</span>`));
        grid.append(cell);
        Charts.bars(host(null, cell), { labels: years.map((y) => (y === "2005" || y === "2025" ? y : "")),
          values: years.map((y) => f.regions[n][y]), height: 78, format: (v) => v.toFixed(1) + " km²",
          max: top, tickFormat: (v) => String(v),
          annotations: [{ from: years.indexOf("2011"), to: years.indexOf("2013"), label: "" }] });
      }
    }
  }
}

/* ---------------- studies tab (unchanged behaviour) ---------------- */
function renderStudies(body) {
  setHeader(0);
  if (!state.stories.length) {
    body.append(el("div", "empty", "No studies registered yet (data/meta/stories.json)."));
    return;
  }
  const active = state.hooks.activeOverlay();
  if (active) {
    const t = state.hooks.overlayTitle(active);
    if (t && state.stories.some((s) => (s.layers || []).includes(active))) {
      body.append(el("p", "stories-note", `Cards about <strong>${t}</strong> first.`));
    }
  }
  const hit = (s) => active && (s.layers || []).includes(active);
  for (const s of [...state.stories.filter(hit), ...state.stories.filter((s) => !hit(s))]) body.append(card(s));
  body.append(el("p", "stories-note",
    "Published findings quote the cited paper (page and figure recorded in stories.json); " +
    "explore cards are open questions, not claims."));
}

function card(s) {
  const c = el("article", "story-card");
  c.dataset.kind = s.kind;
  const head = el("button", "story-head");
  head.setAttribute("aria-expanded", String(state.expanded === s.id));
  head.append(el("span", "story-q", s.question),
              el("span", "pill " + (s.kind === "published" ? "validated" : ""),
                 s.kind === "published" ? "study" : "explore"));
  head.addEventListener("click", () => { state.expanded = state.expanded === s.id ? null : s.id; render(); });
  c.append(head);

  if (state.expanded !== s.id) return c;
  const bd = el("div", "story-body");
  if (s.finding) bd.append(el("p", "story-finding", s.finding));
  if (s.caveat) bd.append(el("p", "story-caveat", "Caveat: " + s.caveat));
  if (s.citation) {
    const p = el("p", "meta", s.citation + (s.doi ? " · " : ""));
    if (s.doi) {
      const a = el("a", null, "doi:" + s.doi);
      a.href = "https://doi.org/" + s.doi; a.target = "_blank"; a.rel = "noopener";
      p.append(a);
    }
    bd.append(p);
  }
  const layers = (s.layers || []).filter((id) => state.hooks.overlayAvailable(id));
  const missing = (s.layers || []).filter((id) => !state.hooks.overlayAvailable(id));
  const actions = el("div", "story-actions");
  if (layers.length || s.camera || s.open_panel) {
    const btn = el("button", "story-show", "Show me on the map");
    btn.addEventListener("click", () => applyCard(s, layers[0]));
    actions.append(btn);
    for (const id of layers.slice(1)) {
      const chip = el("button", "story-chip", state.hooks.overlayTitle(id) || id);
      chip.title = "Switch the map to this layer";
      chip.addEventListener("click", () => applyCard(s, id));
      actions.append(chip);
    }
  } else {
    actions.append(el("span", "meta", "Not in the app yet — no layer to show."));
  }
  bd.append(actions);
  if (missing.length) bd.append(el("p", "meta", "Layer not built in this copy: " + missing.join(", ")));
  c.append(bd);
  return c;
}

async function applyCard(s, layerId) {
  const h = state.hooks;
  if (s.time) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(s.time)) p.set(k, String(v));
    h.presetClimate(p);
  }
  if (layerId) await h.setOverlay(layerId);
  if (s.camera) {
    h.map.flyTo({ center: [s.camera.lng, s.camera.lat], zoom: s.camera.zoom ?? 8,
                  pitch: s.camera.pitch ?? 0, bearing: 0, duration: 1400, freezeElevation: true });
  }
  if (s.open_panel === "lake") h.toggleLake(true);
  /* Studies only: close so the map state (and its legend and time bar) is in full view */
  if (s.open_panel !== "lake") setOpen(false);   // toggleLake already closed it
}
