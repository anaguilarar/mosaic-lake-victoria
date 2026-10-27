/* Side-by-side swipe on the main map (story chapter 4), via @maplibre/maplibre-gl-compare.
   Left = the main map with no overlay (satellite image); right = a second map built from the main
   map's own style, showing one overlay layer. The plugin syncs centre/zoom/bearing/pitch but not the
   camera padding, so the second map takes the same padding (the story pads by the drawer width).
   While open: terrain off and pitch 0 on both maps (the swipe compares flat footprints); Close
   restores the terrain and the pitch. The slider handle is keyboard-operable (arrows, Shift+arrows,
   Home/End) and touch-draggable; on a phone it sits in the top quarter, above the bottom sheet. */

import { ensure } from "./layers.js";

const $ = (s) => document.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

let cmp = null, mapB = null, main = null, saved = null, ui = null, closeBtn = null, onCloseCb = null;
let homeTerrain = null;   // the explorer's terrain spec, remembered whenever it is on (restore fallback)

export const isOpen = () => cmp != null || mapB != null;

/* layers the right-hand map keeps: base, mask, lake, rivers, outlines and labels, plus the overlay */
function rightStyle(style, overlayLayerId) {
  const keep = (l) => l.id === overlayLayerId
    || ["bg", "s2", "hillshade", "lake-fill", "dim", "rivers", "basin-line", "labels-start"].includes(l.id)
    || l.id.startsWith("osm-") || l.id.startsWith("story-") || l.id === "nyando-hl";
  const layers = style.layers.filter(keep).map((l) =>
    l.id === overlayLayerId ? { ...l, layout: { ...(l.layout || {}), visibility: "visible" } } : l);
  const used = new Set(layers.map((l) => l.source).filter(Boolean));
  const sources = Object.fromEntries(Object.entries(style.sources).filter(([k]) => used.has(k)));
  const { terrain, sky, ...rest } = style;          // flat: no terrain, no sky on the comparison side
  return { ...rest, sources, layers };
}

export async function open(map, { overlayLayerId, left, right, padding, onClose, restorePitch }) {
  /* a second call while one is opening (a chapter can be applied twice) must not run: it would save
     the already-flattened view as the state to restore, and Close would leave the terrain off */
  if (isOpen()) return;
  main = map; onCloseCb = onClose;
  if (map.getTerrain()) homeTerrain = map.getTerrain();
  saved = { terrain: map.getTerrain() || homeTerrain, pitch: restorePitch ?? map.getPitch(), maxPitch: map.getMaxPitch() };
  map.setTerrain(null);
  map.setMaxPitch(0);                               // also levels the camera: pitch is clamped to 0

  const box = el("div", "compare-map"); box.id = "mapB";
  map.getContainer().after(box);                    // same parent as #map: the plugin overlays the two
  /* empty style first, error listener attached, then the real style: errors raised while a style is
     set inside the constructor fire before any listener exists and surface only as a bare "Error" */
  mapB = new maplibregl.Map({
    container: box, style: { version: 8, sources: {}, layers: [] },
    center: map.getCenter(), zoom: map.getZoom(), bearing: map.getBearing(), pitch: 0, maxPitch: 0,
    /* the same constraints as the main map: if one map clamps the centre and the other does not, the
       plugin's two-way sync bounces the correction back and forth forever */
    minZoom: map.getMinZoom(), maxZoom: map.getMaxZoom(), maxBounds: map.getMaxBounds(),
    attributionControl: false,
  });
  mapB.on("error", (e) => console.error("compare map:", e.error?.message || e));
  window.__mapB = mapB;                             // debug/probe handle, like window.__map
  await new Promise((res) => mapB.once("load", res));
  if (!mapB) return;                                // closed while loading
  /* diff:false: a diffed setStyle fires no 'style.load'; isStyleLoaded() would also wait for every
     source's tiles, which never settles while the camera is still flying */
  const styled = new Promise((res) => mapB.once("style.load", res));
  ensure(map, overlayLayerId);                // a lazy overlay must be in the style before it is copied
  mapB.setStyle(rightStyle(map.getStyle(), overlayLayerId), { diff: false });
  await styled;
  if (!mapB) return;
  /* padding on the second map only: the main map already flies with the story padding, and setting
     it again mid-flight would stop the camera short of the chapter's view */
  mapB.setPadding(padding || map.getPadding());
  // the main camera may have moved while the second map loaded: line them up before syncing
  mapB.jumpTo({ center: map.getCenter(), zoom: map.getZoom(), bearing: map.getBearing(), pitch: 0 });

  cmp = new maplibregl.Compare(map, mapB, map.getContainer().parentElement, {});
  /* the VISIBLE map: left of the drawer (desktop) - the handle starts in its middle and the keyboard
     range and the reported percentage refer to it, not to the part under the drawer */
  const visibleW = () => map.getContainer().clientWidth - (padding?.right || 0);
  cmp.setSlider(Math.round(visibleW() / 2));

  const swiper = $(".compare-swiper-vertical");
  const pct = () => Math.round((100 * cmp.currentPosition) / visibleW());
  const sync = () => swiper.setAttribute("aria-valuenow", String(pct()));
  Object.assign(swiper, { tabIndex: 0 });
  swiper.setAttribute("role", "slider");
  swiper.setAttribute("aria-label", "Comparison divider: satellite image on the left, observed water on the right");
  swiper.setAttribute("aria-valuemin", "0"); swiper.setAttribute("aria-valuemax", "100");
  sync();
  swiper.addEventListener("keydown", (e) => {
    const W = visibleW(), step = (e.shiftKey ? 0.1 : 0.02) * W;
    const to = { ArrowLeft: cmp.currentPosition - step, ArrowRight: cmp.currentPosition + step,
                 Home: 0, End: W }[e.key];
    if (to == null) return;
    e.preventDefault();
    cmp.setSlider(Math.max(0, Math.min(W, to)));
    sync();
  });
  cmp.on("slideend", sync);

  ui = el("div", "compare-ui");
  ui.append(el("span", "compare-label left", left), el("span", "compare-label right", right));
  map.getContainer().parentElement.append(ui);
  /* its own element: bottom centre of the visible map on desktop (legend and time bar are hidden
     while comparing), top band on a phone (the sheet covers the bottom half) */
  closeBtn = el("button", "compare-close", "Close comparison");
  closeBtn.addEventListener("click", () => close(true));
  map.getContainer().parentElement.append(closeBtn);
  document.body.classList.add("comparing");
}

/* restoreView: put the 3D view back (terrain + pitch) - used by the Close button and on leaving the
   story; a following chapter's flyTo sets its own pitch either way */
export function close(restoreView = true) {
  if (!isOpen()) return;
  try { cmp?.remove(); } catch { /* already gone */ }
  cmp = null;
  mapB?.remove(); mapB = null;
  $("#mapB")?.remove();
  ui?.remove(); ui = null;
  closeBtn?.remove(); closeBtn = null;
  document.body.classList.remove("comparing");
  if (main) {
    main.getContainer().style.clip = "";            // the plugin clips the left map's container
    main.setMaxPitch(saved?.maxPitch ?? 62);
    if (saved?.terrain) main.setTerrain(saved.terrain);
    if (restoreView && saved) main.easeTo({ pitch: saved.pitch, duration: 500, freezeElevation: true });
  }
  saved = null;
  const cb = onCloseCb; onCloseCb = null;
  cb?.();
}
