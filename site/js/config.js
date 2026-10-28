/* Where the app reads its data.
   - Local development (prep/serve.py on 127.0.0.1 / localhost): everything from ../data/  (unchanged behaviour)
   - Published site (GitHub Pages): the small, often-requested files (SITE below) from the repository's own
     data/ folder (../data/), everything else from the Hugging Face dataset
   - Override for testing: ?data=hf uses the published routing (SITE files from ../data/, the rest from
     Hugging Face) on any host; ?data=local reads everything from ../data/
   Use dataUrl(path) for every data file (path relative to the data root, e.g. "meta/layers.json"). */
const HF_DATA = "https://huggingface.co/datasets/aaguilar90/mosaic-lake-victoria/resolve/main/";
const LOCAL_DATA = "../data/";

/* served from GitHub Pages: folder prefixes (ending in "/") or single files. GitHub refuses files over 100 MB:
   terrain.pmtiles is 92.6 MB (2026-10-27); if a rebuild takes it past 100 MB, remove it from this list and
   it falls back to Hugging Face. Also drop it from the release copy (sync_from_basin_app.ps1). */
export const SITE = ["meta/", "series/", "vectors/", "figures/", "fonts/", "climate/", "fire/",
                     "query/flood_query_100m.tif",
                     "tiles/s2_rgb.pmtiles", "tiles/osm_basemap.pmtiles", "tiles/terrain.pmtiles"];

const choice = new URLSearchParams(location.search).get("data");
const isLocal = ["127.0.0.1", "localhost"].includes(location.hostname);
const allLocal = choice === "local" || (choice !== "hf" && isLocal);

const onSite = (path) => SITE.some((s) => (s.endsWith("/") ? path.startsWith(s) : path === s));

export const dataUrl = (path) => (allLocal || onSite(path) ? LOCAL_DATA : HF_DATA) + path;

/* never published (ICPAC basin boundary, licence not specified): with the published routing the app treats
   them as absent without requesting them, so the public site logs no 404s; locally they are probed as usual */
const WITHHELD = ["vectors/basin.geojson", "vectors/basin_mask.geojson"];
export const isWithheld = (path) => !allLocal && WITHHELD.includes(path);
