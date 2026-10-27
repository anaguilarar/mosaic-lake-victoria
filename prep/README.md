# basin_app P0 — data-preparation pipeline

Python ≥3.12 with `rasterio geopandas xarray zarr>=3 fsspec aiohttp requests matplotlib scipy`
plus `pip install pmtiles mercantile pillow`. No GDAL CLI needed (pure rasterio).
Run from `basin_app/prep/`. Outputs land in `basin_app/data/` (see `prep_common.py`). Every script
is re-runnable; intermediates live in `prep/work/` and can be deleted after a successful run.

| # | Script | Output | Runtime |
|---|---|---|---|
| 01 | `01_prep_vectors.py` | `vectors/basin|basin_mask|lake.geojson` | seconds |
| 02 | `02_prep_terrain.py` | `tiles/terrain.pmtiles` (mapbox terrain-rgb, z5–11) | ~10 min |
| 03 | `03_prep_s2.py [--year YYYY]` | `tiles/s2_rgb.pmtiles` (JPEG, z5–12) | ~20–40 min |
| 04 | `04_prep_climate.py [--only precip|temp]` | `climate/*.tif`, `series/*_basin.json` | ~0.5–2 h (network) |
| 05 | `05_prefetch_dahiti.py` | `series/lake_level.json` | seconds — needs `DAHITI_API_KEY` env var |
| 06 | `06_prep_flood.py [--placeholder]` | `tiles/flood_*.pmtiles`, `query/flood_query_100m.tif` | ~30–60 min (real data) |
| 07 | `07_check_hosting.py` | console report | seconds |
| 08 | `08_prep_climate_app.py` | app-ready climate: yearly/seasonal stacks, normals, land mask, per-cell series binaries, land-only basin series | ~1 min (needs 04 outputs) |
| 09 | `09_prep_spi.py` | SPI-3 from the CHIRPS monthly stack (Thom gamma fit, 1991-2020, zero-rain mixed distribution): stack, cell series, basin series | ~1 min |
| 10 | `10_prep_rivers.py` | HydroRIVERS Strahler >= 4 clipped to the basin (downloads the AF zip once); sub-basins passthrough when approved | ~5 min first run |

## Decisions implemented (approved 2026-10-21)

- **Terrain max zoom 11.** Measured on four 60 km windows: downsampling the 30 m DEM to z11
  (76 m) costs 1.4–3.6 m RMSE (p99 ≤ 11 m) against 850–2,700 m of local relief; z12 would halve
  that to 0.7–1.6 m — not visible in a terrain mesh. S2 imagery stays at z12 (native 30 m).
- **S2 stretch:** fixed 0–3000 reflectance + gamma 2.2 for all bands; no per-band percentiles.
- **S2 +1000 offset:** verified handled — lake-water reflectance is 300–460 (min 304) with no
  1000 floor, so the harmonized/offset-corrected collection was used. **Mosaic year still TBD**
  (pass `--year` to 03 when known; written into the attribution).
- **Flood resampling:** nearest for the Web-Mercator warp, mode for overview levels, nearest for
  tile reads — bilinear never touches categorical data. Query COG: **max** of 20 m cells at
  100 m; popover wording fixed to "flooded in up to N of 10 years within 100 m" (in registry).
- **Palettes:** viridis (colour-blind safe, stepped) for years_flooded, flood frequency and
  precipitation; magma for temperature; diverging centred on 0 (BrBG precipitation, RdBu
  temperature) for anomalies; greys ≥50 % for the exclusion layer.
- **DAHITI:** `05_prefetch_dahiti.py` reads **only** `DAHITI_API_KEY`; it never logs the key.
  The old key hard-coded in `scripts/test_wl.py` must be rotated (and that script updated).
- **Licence checks for public deployment:** ICPAC basin (unspecified licence) **and** DAHITI
  data-use terms (free for scientific use; review for a public app) are both flagged in
  `data/meta/layers.json` entries.

## Hosting probe result (07, run 2026-10-21)

Hugging Face `resolve/main` URLs: 307 redirect → CDN answers **206** with correct
`Content-Range`, `Access-Control-Allow-Origin` echoing the Origin, and `Content-Range`/`ETag` in
`Access-Control-Expose-Headers`. **HF dataset repos can host the PMTiles archives** for the app
(fetch follows the redirect). Caveats for P4: per-request redirect adds ~100 ms latency; a plain
object store/CDN or internal server remains the faster option; retest with a >1 GB file once the
real archives exist (large HF files go through the Xet backend).

## P2 decisions (approved)

- Precipitation default = annual total of the latest complete year; MAM/OND totals; anomaly as % of the
  1991–2020 normal (BrBG, centred 100 %). Monthly data only in the click series.
- Temperature: Tmean = (Tmax+Tmin)/2 (labelled as such), Tmax, Tmin; anomaly in °C (RdBu, centred 0,
  Tmean only). Values: magma. Precipitation values: reversed cividis. All distinct from the UI hue #1d5fbf.
- Basin-mean series use land cells only (GLO-30 WBM majority at 0.05°); lake cells stay visible on the
  map and the click panel carries the lake-reliability note.
- Incomplete years are excluded (stacks hold complete seasons/years only; 2026 partial is not offered).
- Per-cell click series: `*_cells.bin` are laid out [row][col][month] so one HTTP Range request returns
  one cell's 548-month series.
- Terrain black-beyond-DEM: fixed by 250 km padded terrain tiles with smoothly extrapolated elevations
  (see 02); camera bounds relaxed accordingly.

## Dev server

PMTiles needs HTTP Range (206). `python -m http.server` does NOT support it (the map stays empty).
Use:  `python prep/serve.py 8765`  then open http://127.0.0.1:8765/site/  (needs `pip install rangehttpserver`).

## Status / to-do

- [x] 01 vectors, 07 probe — done locally.
- [x] 06 with `--placeholder` — synthetic flood tiles + query COG for frontend development
      (`registry entry has "placeholder": true`).
- [x] 02 terrain (89.5 MB, z5–11), 03 S2 (55.7 MB, z5–12; `--year` still TBD), 04 climate (8 COG stacks + 2 series) — done locally 2026-10-21.
- [ ] 05 DAHITI — blocked on key rotation (user).
- [ ] 06 real run — blocked on `analysis/flood_frequency/outputs/` (server job).
- [ ] `tmax/tmin` naming: temperature aggregation uses Tmax/Tmin means; mean temperature is
      (Tmax+Tmin)/2 as a pragmatic proxy, stated in the registry.
