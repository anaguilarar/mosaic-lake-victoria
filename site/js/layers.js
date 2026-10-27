/* Lazy PMTiles layers: a hidden raster layer whose source is a PMTiles archive is kept out of the initial
   style and added (with its source) the first time it is shown. MapLibre reads an archive's header as soon
   as its source is in the style, so this saves one request per archive on page load (~65 archives).
   - split(sources, layers): call once while building the style; returns the eager sources and layers.
   - setVisibility(map, id, "visible" | "none"): use instead of getLayer + setLayoutProperty for any layer.
   - ensure(map, id): add a lazy layer (hidden) without showing it, e.g. before copying the style. */
const lazy = new Map();      // layer id -> { layer, srcId, src }
let order = [];              // every layer id in style order, to insert lazy layers in their place

export function split(sources, layers) {
  order = layers.map((l) => l.id);
  const keep = [];
  for (const l of layers) {
    const src = sources[l.source];
    if (src?.url?.startsWith("pmtiles://") && l.layout?.visibility === "none") lazy.set(l.id, { layer: l, srcId: l.source, src });
    else keep.push(l);
  }
  const used = new Set(keep.map((l) => l.source).filter(Boolean));
  const eager = Object.fromEntries(Object.entries(sources).filter(([id]) => used.has(id) || ![...lazy.values()].some((e) => e.srcId === id)));
  return { sources: eager, layers: keep };
}

export const isKnown = (map, id) => Boolean(map.getLayer(id)) || lazy.has(id);

export function ensure(map, id, visibility = "none") {
  const e = lazy.get(id);
  if (!e) return Boolean(map.getLayer(id));
  if (!map.getSource(e.srcId)) map.addSource(e.srcId, e.src);
  const i = order.indexOf(id);
  const before = order.slice(i + 1).find((x) => map.getLayer(x));
  map.addLayer({ ...e.layer, layout: { ...e.layer.layout, visibility } }, before);
  lazy.delete(id);
  return true;
}

export function setVisibility(map, id, visibility) {
  if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", visibility);
  else if (visibility === "visible" && lazy.has(id)) ensure(map, id, "visible");
}
