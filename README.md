# Lake Victoria Basin Explorer

An interactive web map of the Lake Victoria Basin, built for the MOSAIC project. It brings together terrain,
flood hazard, rainfall, drought, population, tree-cover change, land cover and fire, 1981–2026, with a
"Uses & studies" drawer: a scroll-driven story ("From the Mau to the lake") and cards summarising published
studies of the basin.

- **Live app:** https://anaguilarar.github.io/mosaic-lake-victoria/site/
- **Data:** https://huggingface.co/datasets/aaguilar90/mosaic-lake-victoria (served to the app from there)
- **Data report:** [`DATA_REPORT.md`](DATA_REPORT.md): what each layer is, how it was made, its caveats and
  references.

The app is a static site (HTML, CSS and JavaScript ES modules, no build step). MapLibre GL JS, PMTiles,
maplibre-gl-compare and geotiff.js load from jsDelivr at pinned versions; fonts from Google Fonts.

## Repository layout

| Path | Content |
|---|---|
| `site/` | The app: `index.html`, `css/`, `js/` (ES modules), `assets/` |
| `site/js/config.js` | Where the app reads its data: the `SITE` list (served from this repository) and the Hugging Face dataset (everything else) |
| `data/` | The small, often-requested data files served by GitHub Pages: meta, series, vectors, figures, fonts, climate, fire, the flood click raster, and the satellite, terrain and place-name tiles |
| `prep/` | The Python pipeline that built the data, and the local server (`prep/README.md`, `prep/requirements.txt`) |
| `DATA_REPORT.md`, `STYLE.md` | Data report (linked from the app) and the app's style notes |
| `index.html`, `.nojekyll` | Redirect to `site/`; serve files as they are on GitHub Pages |

About 340 MB of data is in `data/` here; the rest (about 0.8 GB of map tiles and click-query rasters) is in the Hugging Face dataset. `terrain.pmtiles` (92.6 MB) is close to GitHub's 100 MB file limit: if a rebuild takes it past 100 MB, remove it from `SITE` in `config.js` and from `sync_from_basin_app.ps1`, and the app reads it from Hugging Face.

## Run it locally

Python 3.12 with `rangehttpserver` (`pip install rangehttpserver`). From the repository root:

```
python prep/serve.py 8765
```

Then open one of:

- `http://127.0.0.1:8765/site/?data=hf`: the published routing: `SITE` files from `data/` here, the rest from Hugging Face;
- `http://127.0.0.1:8765/site/?data=local`: everything from the local `data/` folder (download the Hugging Face
  dataset into `data/` first). This is also the default on `127.0.0.1` and `localhost`.

On any other host (GitHub Pages) the app uses the published routing. `?data=hf` / `?data=local` override this.

The pipeline in `prep/` expects the full working project (inputs and the flood-frequency analysis outputs one
level up) and is published as reference code; see `prep/README.md`.

## Data sources and licences

Each layer keeps its source's licence. Full citations: `DATA_REPORT.md` §4 and the Hugging Face dataset card.

| Layer | Source | Licence |
|---|---|---|
| Flood hazard (years flooded, frequency, maximum extents) | Copernicus EMS Global Flood Monitoring (Sentinel-1), 20 m, 2016–2025 | Copernicus EMS, free with attribution |
| Terrain; lake outline | Copernicus DEM GLO-30 and its water-body mask | Free with attribution |
| Satellite imagery | Sentinel-2 L2A median mosaic 2023–2025 | Free with attribution |
| Precipitation; drought (SPI-3) | CHIRPS v3.0 (UCSB Climate Hazards Center) | CC-BY-4.0 |
| Temperature | CHIRTS-ERA5 (UCSB Climate Hazards Center) | CC-BY-4.0 |
| Lake level | DAHITI (DGFI-TUM) satellite altimetry | CC BY-NC 4.0 (DAHITI terms of use; non-commercial use only); attribution: DAHITI, DGFI-TUM |
| Rivers; sediment sub-catchments | HydroRIVERS / HydroSHEDS v1 (sub-catchments use sample sites from Humphrey et al. 2025) | HydroSHEDS v1 licence (WWF); attribution below |
| Population (exposure input) | WorldPop constrained 2020, 100 m | CC-BY-4.0 |
| Tree-cover loss | Hansen Global Forest Change GFC-2025-v1.13 | CC-BY-4.0 |
| Land cover | Esri/Impact Observatory annual LULC v2; ESA WorldCover 2021 v200 | CC BY 4.0 |
| Active fires; burned area | NASA FIRMS VIIRS; MODIS MCD64A1 v6.1 | NASA open data, attribution |
| Place names (basemap) | OpenStreetMap via Protomaps | ODbL 1.0 (share-alike), © OpenStreetMap contributors |
| Admin boundaries | geoBoundaries gbOpen ADM1/ADM2 | Per boundary (Public Domain, CC0, CC BY 4.0, CC BY 3.0 IGO, ODbL for Uganda and Tanzania ADM1) |
| Basin boundary | ICPAC geoportal (2019) | Not specified by the source |

**HydroSHEDS.** HydroSHEDS-derived layers (rivers, sub-catchments) are included for display in this app only and may not be redistributed separately. © World Wildlife Fund, Inc. (2006-2022), used under licence. This product MOSAIC Lake Victoria Basin Explorer incorporates data from the HydroSHEDS version 1 database which is © World Wildlife Fund, Inc. (2006-2022) and has been used herein under license. WWF has not evaluated the data as altered and incorporated within MOSAIC Lake Victoria Basin Explorer, and therefore gives no warranty regarding its accuracy, completeness, currency or suitability for any particular purpose. Portions of the HydroSHEDS v1 database incorporate data which are the intellectual property rights of © USGS (2006-2008), NASA (2000-2005), ESRI (1992-1998), CIAT (2004-2006), UNEP-WCMC (1993), WWF (2004), Commonwealth of Australia (2007), and Her Royal Majesty and the British Crown and are used under license. The HydroSHEDS v1 database and more information are available at https://www.hydrosheds.org. Scientific citation: Lehner, B., Verdin, K., Jarvis, A. (2008): New global hydrography derived from spaceborne elevation data. Eos, Transactions, AGU, 89(10): 93-94.

The flood layer is a hazard proxy (how often open floodwater was observed), not flood risk.

## Licence

Licence: to be added.
