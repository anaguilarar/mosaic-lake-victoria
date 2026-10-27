# Lake Victoria Basin Explorer — data report

**21 October 2026.** This report lists the data integrated in `basin_app`: what each layer shows, why it is included, where it comes from, and how it was processed. Facts come from the app registry (`data/meta/layers.json`), the prep logs, and `analysis/flood_frequency/ACCESS.md`.

**Status of items still pending:**
- **Flood hazard:** real Copernicus GFM layer (2016–2025), under internal review before external use. Masking
  rules are settled (§3.1) and the 2020 comparison with Pietroiusti et al. (2024) is largely done (§3.1, last part).
  Still open: two straight-line artefacts, a possible false-detection cluster on the Serengeti–Mara plains, and
  the re-run of the 2020 comparison on the rebuilt layers.
- **Exposure summaries:** people living in cells where water was detected in ≥ N years (2016–2025), WorldPop 2020; shown in the story's chapter 5 and described in the Population note (§2) below.
- **Sentinel-2:** delivered mosaic covers the full basin bbox (verified, zero nodata); the exact export script is being confirmed for the record.

---

## 1. Layers at a glance

| Layer | What it shows | Source | Resolution · period | Why it is included (study basis) |
|---|---|---|---|---|
| Basin boundary | Basin outline and outside-basin mask | ICPAC geoportal (`lv_basin`) | vector · 2019 | Common study extent for all layers. It matches the basin size reported by Liu et al. (2022) and Khaki & Awange (2019). |
| Terrain | 3D relief | Copernicus DEM GLO-30 | 30 m (tiled to ~76 m, z11) · static | Gives the 3D view of the basin's upstream–downstream relief (Liu et al. 2022). |
| Lake / water mask | Lake and river surface | GLO-30 water body mask | 30 m · static | Removes permanent water from the flood layer and from basin rainfall means. Pietroiusti et al. (2024) used the same mask. |
| Satellite imagery | True-colour base map | Sentinel-2 L2A median composite (`COPERNICUS/S2_SR_HARMONIZED`) | 30 m · 2023–2025 | Visual context for every other layer. |
| Rivers | Main river network (Strahler ≥ 4) | HydroRIVERS v1.0 (HydroSHEDS) | vector · static | Shows which rivers drain where. Liu et al. (2022) built their basin model on HydroSHEDS. |
| Place names | Cities, towns, villages, lakes, rivers, protected areas (labels only) | OpenStreetMap via Protomaps | vector · build 2026-10-22 | Reference for reading every other layer. |
| Admin boundaries | ADM1/ADM2 units of the five countries, with names on click | geoBoundaries (gbOpen) | vector · 2006–2021 by country | Reference units for county and district reporting. |
| Lake water level | Lake level time series, 1992-10-17 to 2026-09-14 | DAHITI (DGFI-TUM) altimetry, target id 2 | point series · ~10-day | Shows the 2019–2020 rise and the record high of May 2024 (DAHITI). Pietroiusti et al. (2024) used DAHITI; Ali et al. (2024) and Khaki & Awange (2019, 2021) also used satellite altimetry. |
| Precipitation | Annual, MAM and OND totals; anomaly vs 1991–2020 | CHIRPS v3.0 daily | 0.05° (~5.5 km) · 1981–2025 | Main driver of lake level and floods. Liu et al. (2022) used CHIRPS; Pietroiusti et al. (2024) compared CHIRPS with other products; Khaki & Awange (2021) linked the 2019–2020 rise to the short rains. |
| Temperature | Tmax, Tmin, Tmean = (Tmax+Tmin)/2; anomaly | CHIRTS-ERA5 daily | 0.05° · 1981–2025 | Long-term warming signal. Liu et al. (2022) used ERA5 temperature; Ali et al. (2024) analysed land-surface temperature. |
| Drought (SPI-3) | 3-month Standardized Precipitation Index | Derived from CHIRPS v3.0 | 0.05° · 1981-03 to 2026-08, monthly | Drought counterpart to the flood layer. Liu et al. (2022) characterised drought with the 3-month SRI, the runoff equivalent of SPI. |
| Flood hazard | Years flooded (0–10), flood frequency, share of observations excluded | Copernicus EMS Global Flood Monitoring (GFM) | 20 m · 2016–2025 | Where floods recur. Pietroiusti et al. (2024) mapped the 2020 floods with LIST's HASARD algorithm, which is one of the three GFM algorithms. |
| Population | People per ~100 m cell, used as exposure input | WorldPop 2020, constrained (KEN, UGA, TZA, RWA, BDI) | 100 m · 2020 | Who lives in flood-prone areas. Follows Pietroiusti et al. (2024), who overlaid flood maps on WorldPop. |
| Tree-cover loss | Year of loss and tree cover in 2000; the map shows cumulative loss in 5-year epochs | Hansen Global Forest Change GFC-2025-v1.13 | 30 m · 2001–2025 | Upper-catchment clearance. Linked to land-cover change (Mugo et al. 2020; Liu et al. 2022) and to sediment sources (Humphrey et al. 2025). |
| Land cover | Annual land-cover classes (9-class) | Esri/Impact Observatory LULC v2, via Planetary Computer | 10 m, shown at 30 m · 2017–2023 | Cropland and built-area expansion context (Mugo et al. 2020; Liu et al. 2022; Ali et al. 2024). Cropland read with caution (Kerner et al. 2023). |
| Land cover reference | Single-year class snapshot | ESA WorldCover v200 | 10 m, shown at 30 m · 2021 | Cross-product check: global land-cover products disagree on cropland in sub-Saharan Africa (Kerner et al. 2023). |
| Fire density | Active-fire detections per km² per year | NASA FIRMS VIIRS, S-NPP only | ~1 km · 2012–2025 | Savanna and crop-residue burning as a land-management signal. |
| Fire points | Individual active-fire detections (confidence nominal/high) | NASA FIRMS VIIRS S-NPP + NOAA-20 | 375 m points · 2012–2025 (NOAA-20 from 2020) | Detail behind the density layer, visible from zoom 10. |
| Burned area | Cells burned at least once in the year | MODIS MCD64A1 v6.1, via Planetary Computer | ~500 m · 2001–2025 | Burned extent complements point detections (Giglio et al. 2018). |
<!-- auto:table:land-fire — the five rows above are maintained by prep/14_data_report.py -->

All layers are prepared offline in Python (`basin_app/prep/`) and served as static files: PMTiles for map tiles, small COGs for click queries, and JSON for time series. No backend is used.

---

## 2. Notes per dataset

**Basin boundary.** ICPAC geoportal, `geonode:lv_basin`. The geoportal states the licence as "not specified", so redistribution must be confirmed before any public release.

<!-- auto:layer:rivers start -->
**Rivers.**
- HydroRIVERS v1.0, Strahler ≥ 4, clipped with the native-resolution lake shoreline; 1,076 reaches.
- The Yala main stem (Strahler ≥ 4) ends at the Yala Swamp, about 6 km from open water; only lower-order swamp channels reach the lake (HydroRIVERS v1.0).
<!-- auto:layer:rivers end -->

**Terrain and water mask.**
- Copernicus DEM GLO-30, exported as two overlapping rectangles that together cover the whole basin polygon (100% real elevation inside the basin). It was warped to Web Mercator and encoded as terrain-RGB tiles up to zoom 11.
- The corners outside both rectangles, and a 600 km display margin, are filled with smooth synthetic relief so the 3D view has no void. These areas are all outside the basin; elevation is never shown or queried there. Their edge shows as a faint line in the hillshade (for example at 31.0°E, 1.0°N).
- Zoom 11 was chosen on measured evidence: 1.4–3.6 m RMSE against 850–2,700 m of local relief.
- The 3D view uses a 1.8× vertical exaggeration by default.
- The water body mask classes are 2 for lake and 3 for river.

**Sentinel-2 imagery.**
- A median composite of all Sentinel-2 L2A images from 1 January 2023 to 31 December 2025 (`COPERNICUS/S2_SR_HARMONIZED`, Google Earth Engine). Clouds, cloud shadows and cirrus were masked with the Scene Classification Layer (classes 3, 8, 9, 10) before the median.
- Bands B4, B3, B2 were exported at 30 m in EPSG:4326 as reflectance × 10,000.
- Shown with one fixed stretch for all three bands (reflectance 0–3000, gamma 2.2).
- The post-2022 +1000 reflectance offset was verified as corrected: lake reflectance is 300–460, with no 1000 floor.

**Lake water level.**
- DAHITI database (Schwatke et al. 2015), accessed through its registered API.
- Values are water-surface elevations, each with an uncertainty, from multi-mission satellite altimetry.
- The API key is kept on the preparation machine and never reaches the app.

**Precipitation and temperature.**
- Daily CHIRPS v3.0 and CHIRTS-ERA5, read from Zarr copies on Hugging Face and aggregated offline to monthly, seasonal (MAM long rains, OND short rains) and annual values.
- Anomalies are expressed against 1991–2020: % of normal for rainfall, °C for temperature.
- Basin means use **land cells only**, because satellite rainfall over the lake surface is less reliable.
- Incomplete years are not offered.

**Population.**
- WorldPop 2020 constrained, 100 m. No newer constrained release was available when the layer was built.
- It is shown as an **exposure input**, not as risk.
- The flood-exposure summary weights population by the fraction of each 100 m cell flooded in at least N years. Each 20 m flood cell is assigned to the 100 m WorldPop cell containing its centre. This replaced an area-weighted version (fractional overlap of the 20 m cells); on test crops the two differ by −1 % to +4 %.

**Tree-cover loss.**
- Hansen et al. (2013), version GFC-2025-v1.13. Loss is counted only where tree cover in 2000 was at least 30%.
- Total loss in the basin, 2001–2025: about 4,866 km².
- This is tree-cover loss, not deforestation: it includes plantation and woodlot harvest.
- Detection improved around 2011–2013, so annual values before and after that period are not strictly comparable.

<!-- auto:layer:landcover start -->
**Land cover (Esri/Impact Observatory).**
- Annual LULC v2, 10 m, from Sentinel-2 (Karra et al. 2021), streamed from the Planetary Computer (io-lulc-annual-v02) and resampled to the 30 m basin grid with nearest neighbour only (categorical).
- Years 2017–2023; no 2024 release was available on the Planetary Computer when built (probed 21 Oct 2026).
- Licence CC BY 4.0. Per-year class areas are written for the basin (sub-basins join after approval).
- **Caveat:** global land-cover products disagree on cropland in sub-Saharan Africa (Kerner et al. 2023); year-to-year change is indicative.
<!-- auto:layer:landcover end -->

<!-- auto:layer:worldcover start -->
**Land cover reference (ESA WorldCover 2021).**
- WorldCover v200, 10 m, shown at 30 m as a static cross-check layer. Licence CC BY 4.0 (Zanaga et al. 2022).
<!-- auto:layer:worldcover end -->

<!-- auto:layer:fire start -->
**Active fires (VIIRS).**
- NASA FIRMS archive country CSVs, filtered to the basin bbox and to confidence nominal/high.
- The **density time series uses S-NPP only (2012–2025)** for cross-year consistency; it is detections per km² per year on a ~1 km grid.
- **NOAA-20 appears only in the point layer** (its archive starts in 2020); points carry sensor, date and fire radiative power and show from zoom 10.
- **Caveats:** active fires are mostly savanna and crop-residue burning; charcoal production is not detected reliably; cloud cover hides wet-season fires.
<!-- auto:layer:fire end -->

<!-- auto:layer:burned_area start -->
**Burned area (MODIS MCD64A1 v6.1).**
- Monthly Burn_Date rasters from the Planetary Computer, combined to an annual "burned at least once" mask per ~500 m cell, 2001–2025; annual burned km² per region accompany the layer.
- Annual burned area in the basin, all 25 years 2001–2025: minimum about 4,100 km² (2017), median about 10,300 km², maximum about 15,300 km² (2003).
- **Caveat:** ~500 m detection misses small and low-intensity burns; cloud limits wet-season detection.
<!-- auto:layer:burned_area end -->

**Place names (OpenStreetMap).**
- Labels only: countries, cities and towns by zoom, villages from zoom 11, lakes and bays, rivers (from zoom 9), and national parks, reserves and forests (from zoom 8). No roads, buildings or fills are drawn.
- Extracted from the Protomaps daily OSM basemap (build 2026-10-22, schema v4) for the basin bbox up to zoom 12 with `pmtiles extract`; 67 MB. Fonts (Noto Sans) are hosted with the app.
- On by default; drawn above the thematic layers, with the story labels taking priority where they collide.
- Names just outside the basin (e.g. Goma, Bukavu, Nakuru) appear because the extract is the bounding rectangle.
- **Caveat:** volunteered data; coverage and spelling vary, and label points are OSM positions, not an official gazetteer.

**Admin boundaries (geoBoundaries).**
- ADM1 and ADM2 for Kenya, Uganda, Tanzania, Rwanda and Burundi (gbOpen), clipped to the basin and simplified to ~100 m; 50 ADM1 and 311 ADM2 units. Clicking the map shows the unit names and the country.
- Off by default. Each boundary keeps its own source licence, which differs by country and level: Public Domain (Kenya ADM1, Uganda ADM2, Burundi ADM2), CC0 (Burundi ADM1), CC BY 4.0 (Rwanda), CC BY 3.0 IGO (Kenya and Tanzania ADM2) and ODbL (Uganda and Tanzania ADM1, from OpenStreetMap).
- **Caveat:** boundaries are indicative, not an official delimitation. Boundary years range from 2006 (Uganda ADM2 counties) to 2021 (Tanzania districts). Uganda and Tanzania ADM1 derive from OpenStreetMap (ODbL): if the boundary file is redistributed, those parts stay under ODbL with attribution (share-alike). GADM is not used.

**Sub-basins (Nzoia, Yala, Nyando, Sondu-Miriu).**
- Derived from HydroBASINS, with the level chosen to match the HydroRIVERS upstream area at each outlet (`analysis/flood_frequency/scripts/06_derive_subbasins.py`, settings in `config.toml` [subbasins]): Nzoia 13,094 km², Yala 3,083 km², Nyando 3,735 km², Sondu-Miriu 3,483 km²; no two units overlap.
- The 5 % tolerance for the HydroBASINS level is checked against the HydroRIVERS upstream area at the outlet reach, not against published catchment areas (those only guide the outlet search).
- At the Nyando mouth, one HydroBASINS unit also drains the gulf shoreline directly to the lake (nine HydroRIVERS reaches that never join the Nyando). That unit is split by nearest reach and only the Nyando part is kept: 173 km² of shoreline drainage is clipped, leaving the Nyando within 0.4 % of its HydroRIVERS upstream area.
- HydroRIVERS routes the Yala into the Nzoia inside the Yala Swamp; the Yala is kept as its own unit and subtracted from the Nzoia, so the Nzoia includes the Budalangi delta.
- The Nyando outlet is the last reach before the Winam Gulf (HydroRIVERS 11000013); the automatic search had picked a reach about 15 km upstream that left out the Awach Kano and Nyaidho.

**Uses & studies panel.** The "Uses & studies" drawer (right side) has two tabs. *Story* is a scrolling
narrative ("From the Mau to the lake", 10 chapters): each chapter sets the map to the layers, period and view it
describes, and its figures are rendered from the app's own layers (prep/90_story_figures.py). *Studies* lists
published work on the basin that uses the same kinds of data, with the full reference and a link. Figures quoted in
either tab come only from the cited paper or from the app's layers as documented in this report. No numbers are
derived by combining sources. Chapters that depend on layers still under review are marked "provisional".

---

## 3. Methods

### 3.1 Flood hazard: observed flood frequency, 2016–2025

**Data.** The Copernicus EMS Global Flood Monitoring (GFM) archive (Salamon et al. 2021):
- A flood map for every Sentinel-1 acquisition since 2015, at 20 m, in the Equi7Grid Africa projection.
- Each map is an **ensemble of three flood-detection algorithms**, by DLR, TU Wien and LIST. The LIST algorithm is the hierarchical split-based approach of Chini et al. (2017), the method behind HASARD used by Pietroiusti et al. (2024).
- Because these maps already exist, **no flood detection was re-implemented**.
- The files are read anonymously from the EODC STAC API (collection `GFM`). About 25,200 items cover the basin from 2016 to 2025.

**Counting per pixel.** Image slices from the same orbit pass are merged first. Then:
- `n_obs` = passes where the pixel was observed;
- `n_excl` = observed passes where GFM's exclusion mask flags the pixel. These are areas where GFM does not assess floods, such as dense vegetation, radar shadow and urban areas;
- `n_flood` = passes classified as flooded;
- `n_valid = n_obs − n_excl`.

**Derived values.**
- **Years flooded** (main map layer): the number of calendar years, 0–10, with at least one flood detection. Shown wherever the land was observed.
- **Flood frequency** = `n_flood / n_valid`. It is always divided by valid observations, because the number of Sentinel-1 passes fell by about 40% after Sentinel-1B failed in December 2021.
- **Not assessed (GFM exclusion)** = share of observations excluded by GFM (`n_excl / n_obs`), shown as its own layer.
- **Maximum extents, April–July 2020 and April–May 2024:** observed water outside the 2011–2015 lake. This is GFM's `ensemble_water_extent` minus the GLO-30 water-body mask, the same definition Pietroiusti et al. (2024) used for 2020. It includes the shoreline fringe flooded by the high lake, which GFM's flood layer treats as normal water.

**Masks and rules.**
- **Permanent water only** is removed: the GLO-30 water-body classes (ocean, lake, river), plus pixels that GFM's monthly reference-water masks mark as water in all 12 calendar months. A month counts as water if any Equi7 tile covering the pixel shows water that month. Seasonal water is not removed; GFM already excludes each month's usual water from its flood map.
- **The exclusion rule applies to flood frequency only.** Where GFM excluded ≥ 50% of a pixel's observations, frequency is "not computed". GFM excludes only pixels it classified as *non-flooded*, so in those areas the denominator shrinks while flood detections remain, and the ratio would be inflated.
- **Years flooded and the maximum extents keep every detection.** A detection in a low-sensitivity area is still evidence of flooding. Where most observations were excluded, the click panel adds: "Radar sensitivity low here; absence of floods is uncertain."
- **Pixels with fewer than 50 valid observations** get no frequency value.
- No likelihood threshold is applied in the full run.

**Display.**
- Reprojection uses nearest-neighbour resampling, never smoothing.
- At small scales, the flood-extent, years-flooded and flood-frequency tiles show the **maximum** of the cells inside each display pixel, so narrow floodplains stay visible when zoomed out. A pixel is coloured if any part of it flooded; for years and frequency, it shows the highest value in that area. The "Not assessed" layer uses the most common value instead, so exclusion is not exaggerated.
- Click queries read a 100 m version that takes the **maximum** of the 20 m cells. The popup reads "flooded in up to N of 10 years within 100 m".

**Interpretation and limits.**
- This is a **flood-hazard proxy, not flood risk**. It shows how often open floodwater was observed, not depth, return period, exposure or vulnerability.
- Floods under vegetation and in towns are under-detected, and floods shorter than the 6–12-day revisit can be missed.
- Data up to mid-2024 come from the reprocessed GFM archive and later data from near-real-time processing, so results are reported per year to make any step change visible.

**Straight lines in the western basin: one artefact, one river.**
- **Streak 1, southern Rwanda (masked).** A single straight line of flood detections from 29.533 °E, 2.424 °S to 30.282 °E, 2.258 °S (85 km, bearing 77.5°), all from one Sentinel-1 pass on 31 January 2021, 16:20 UTC (ascending): 11,801 detections (4.72 km²) within 800 m of the line. It runs perpendicular to the Sentinel-1 track and does not follow rivers (25 % of the detections lie within 300 m of a HydroRIVERS reach). It is treated as an artefact. That pass's detections within 800 m of the line are removed from the 2021 counts, except the 2,961 that could be real water (JRC GSW occurrence > 0, or within 300 m of a river or lake): 8,840 detections (3.54 km²) masked (`config.toml` [masks]; scripts 28, 36 and 37). The observations stay valid and every other date is untouched. Without the mask the line would count as one flooded year on the map and in the exposure counts for cells flooded at least once.
- **Streak 2, Burundi–Tanzania (real water, not masked).** A straight-looking line from 30.202 °E, 3.301 °S to 30.764 °E, 2.466 °S (112 km) is the Ruvubu River: 97 % of its detections lie within 300 m of the HydroRIVERS channel (median 138 m). A narrow river at 20 m resolution is detected only when it runs high.

**Serengeti–Mara look-alikes (around 34.5° E, 2.2° S), masked.** Over protected grassland in the western Serengeti (10,292 km² zone; 98.8 % grassland in WorldCover 2021), GFM detected water on 3,927 km² in at least one year, away from the main river channels. None of these pixels has ever recorded water in JRC Global Surface Water (Landsat, 1984–2021). The detections peak in near-normal years (2016, 2017, 2025: 2,200–2,650 km²) and almost vanish in 2020 (85 km²), the wettest long rains of the period. Only 1 % of the zone's detections fall in March–May, the main rainy season; 52 % fall in October–December (short rains) and 47 % in the dry months. Real flooding would show the opposite pattern. We therefore treat them as radar look-alikes and show the zone as "Not assessed" for all years; it is excluded from the exposure figures. Similar look-alikes may occur on grassland just outside the zone, where they cannot be separated from real flooding on the Simiyu and Speke Gulf floodplains. In a sample of four 5 × 5 km windows over all 2017 passes (715,104 detection pixels), 82 % of detections came from passes carrying GFM's 'low regional backscatter' advisory flag (40–99.7 % by window).

**Comparison with the published 2020 flood map.** The April–July 2020 extent was compared with Fig. 5 of Pietroiusti et al. (2024), which used LIST's HASARD algorithm alone, box by box.
- **Area within 50 km of the shore:** ≤ 312.3 km² of water outside the 2011–2015 lake within 50 km of the shore (upper bound: measured over 1 Apr–31 Jul 2020, which contains Pietroiusti et al.'s 5 Apr–30 Jun window), against their ~642.5 km². Ours is the GFM ensemble water extent minus a static lake mask; theirs is HASARD flood detections.
- **Agreement:**
  - The Nzoia–Yala floodplain (box 1) matches.
  - The Speke Gulf shore at the Grumeti–Mbalangeti mouth (box 7) and the Simiyu area (box 8) match in location. All three GFM algorithms detect the flooding there.
  - Compared at the published figure's resolution (~0.43 km² per pixel); areas from the figure are not used.
- **Disagreement, box 7 east** (a cluster of flooding east of the river mouth, east of the Speke Gulf head):
  - About two-thirds of that cluster (63 % of its figure pixels) lies on land where GFM can map water, and GFM confirms only 3.7 % of it. The remaining third lies on land GFM excludes, so it cannot be assessed.
  - JRC Global Surface Water (Landsat) finds no water there in May or June 2020; April was too cloudy to check optically.
  - These detections are therefore not supported by the other evidence available.
- **Limits of the optical check.** GSW also misses flooding along the gulf shore that all radar algorithms detect, probably flooded vegetation or shallow water. Its May–June coverage rests on only 2–4 usable dates per month. Its absence of water is supporting evidence, not proof.
- **Panel wording for the 2020 layer:** "Pietroiusti et al. (2024) map additional flooding east of the Speke Gulf head. Neither GFM's algorithms (on mappable land) nor JRC Global Surface Water (May–June 2020) confirm it; April 2020 could not be checked optically because of cloud, and part of the area is outside GFM's mappable zone."

**Box by box, at the figure's resolution** (this app's analysis). Ours: Apr–Jul 2020 (GFM, definition C, masked); Fig. 5: 5 Apr–30 Jun 2020 (HASARD). Our window is longer, so differences in the 'we show more' direction are partly expected. Both sides exclude the 2011–2015 lake. Pixel counts are figure pixels (~0.43 km² each); “a / b” = % of Fig. 5 pixels we also flag / % of our pixels Fig. 5 also flags.

| Box | Ours, km² (20 m) | Figure pixels: Fig. 5 only / ours only / both | Strict a / b (%) | ±1 px a / b (%) | Class¹ |
|---|---|---|---|---|---|
| 1 Nzoia–Yala | 20.8 | 53 / 207 / 140 | 72.5 / 40.3 | 96.9 / 66.0 | agrees |
| 2 Sondu–Nyando | 24.5 | 43 / 191 / 77 | 64.2 / 28.7 | 99.2 / 52.2 | agrees |
| 3 Olare | 1.3 | 4 / 24 / 12 | 75.0 / 33.3 | 100 / 72.2 | agrees |
| 4 Kuja | 3.8 | 24 / 35 / 36 | 60.0 / 50.7 | 98.3 / 76.1 | agrees |
| 5 Mara River | 43.7 | 324 / 462 / 268 | 45.3 / 36.7 | 93.2 / 67.9 | agrees |
| 6 Makojo | 2.4 | 146 / 90 / 16 | 9.9 / 15.1 | 29.0 / 50.0 | Fig. 5 shows more |
| 7 Grumeti–Mbalangeti² | 17.5 | 699 / 144 / 71 | 9.2 / 33.0 | 19.5 / 65.6 | Fig. 5 shows more |
| 8 Simiyu | 7.1 | 44 / 100 / 21 | 32.3 / 17.4 | 81.5 / 61.2 | agrees |
| 9 Magongo–Isanga | 91.7 | 678 / 628 / 281 | 29.3 / 30.9 | 53.6 / 55.2 | agrees |
| 10 Muleba | 2.9 | 252 / 105 / 43 | 14.6 / 29.1 | 28.5 / 53.4 | Fig. 5 shows more |
| 11 Bukoba² | 19.3 | 331 / 211 / 109 | 24.8 / 34.1 | 49.5 / 60.9 | partial overlap |
| 12 Masaka–Ssese | 6.0 | 119 / 88 / 110 | 48.0 / 55.6 | 86.5 / 79.3 | agrees |
| 13 Entebbe–Kampala | 12.5 | 81 / 327 / 216 | 72.7 / 39.8 | 99.0 / 73.7 | agrees |
| All 13 boxes | 253.5 | 2,798 / 2,612 / 1,400 | 33.3 / 34.9 | 59.3 / 63.5 | agrees |
| Whole 50 km area | 312.3 | 4,350 / 5,993 / 2,508 | 36.6 / 29.5 | 70.5 / 63.3 | agrees |

Boxes 6, 7 and 10 (Fig. 5 shows more), share of their Fig. 5-only pixels on land GFM excludes (GFM's own 2016–2025 excluded share ≥ 50 %, before the Serengeti–Mara zone mask): box 6, 73 % (mostly on land GFM excludes); box 7, 28 %: 30 % of the 587 pixels inside the zone and 17 % of the 112 outside it (not explained by GFM's exclusion mask); box 10, 94 % (mostly on land GFM excludes). Boxes 6 and 10 have no pixels in the zone.

¹ Classes, applied mechanically on the ±1-pixel agreement; F = Fig. 5 pixels, O = our pixels, a = % of F we also flag, b = % of O that Fig. 5 also flags; the first rule that applies: neither shows flooding (F < 5 and O < 5); agrees (a ≥ 50 % and b ≥ 50 %); Fig. 5 shows more (F ≥ 1.5 × O and b ≥ 50 %); we show more (O ≥ 1.5 × F and a ≥ 50 %); partial overlap (everything else).

² Box 7: the shore at the river mouth matches; most of Fig. 5's extra pixels are the cluster east of the river mouth described under “Disagreement, box 7 east” above. 587 of the 699 Fig. 5-only pixels fall inside the Serengeti–Mara zone, which this app shows as 'Not assessed' (§3.1). There, neither GFM nor JRC Global Surface Water supports the flooding shown in Fig. 5, and this comparison cannot decide between the two methods. Box 11: the panels show different features inland, while the shoreline matches.


### 3.2 Drought: SPI-3

The Standardized Precipitation Index (McKee et al. 1993) shows how unusual rainfall is for a given place and season, in standard-deviation units.

1. **3-month totals.** For each 0.05° cell, monthly CHIRPS v3.0 rainfall is summed over a rolling 3-month window, labelled by the window's last month. For example, August = June–August.
2. **Distribution fit.**
   - For each cell and calendar month, a gamma distribution is fitted to the 30 totals of 1991–2020, using the Thom (1958) approximation.
   - Months with zero rain are handled with a mixed distribution: *p = q₀ + (1 − q₀)·Gamma CDF*, where *q₀* is the share of zero-rain windows.
3. **Standardisation.** The cumulative probability of each total is converted to a standard normal value, and the result is limited to ±3.
4. **Reading the values.**

   | SPI | Meaning |
   |---|---|
   | ≤ −1 | Moderately dry |
   | ≤ −1.5 | Severely dry |
   | ≤ −2 | Extremely dry |
   | Positive | Wetter than normal |

   SPI is relative to each cell's own normal for that season. A dry season can therefore show strongly negative SPI even though it is normally dry.
5. **Quality checks.**
   - Cells with a low normal (< 30 mm) or many zero-rain windows (q₀ > 20%) are flagged.
   - For August 2026, only 3% of the cells below −2.5 carried that flag.
   - The most recent 2–3 CHIRPS months are **provisional**, because they include fewer station observations than the final data.

---

## 4. References

**Studies (`bibliography/`)**
- Ali, M., Ali, T., Gawai, R., Dronjak, L., Elaksher, A. (2024). The analysis of land use and climate change impacts on Lake Victoria Basin using multi-source remote sensing data and Google Earth Engine. *Remote Sensing* 16, 4810. doi:10.3390/rs16244810
- Humphrey, O.S. et al. (2025). Sediment and soil source apportionment using geochemical fingerprinting techniques in the Winam Gulf, Lake Victoria. *Catena* 255, 109053. doi:10.1016/j.catena.2025.109053
- Khaki, M., Awange, J. (2019). Improved remotely sensed satellite products for studying Lake Victoria's water storage changes. *Science of the Total Environment* 652, 915–926. doi:10.1016/j.scitotenv.2018.10.279
- Khaki, M., Awange, J. (2021). The 2019–2020 rise in Lake Victoria monitored from space. *Sensors* 21, 4304. doi:10.3390/s21134304
- Liu, Y. et al. (2022). Hydrological impacts of land use/cover changes in the Lake Victoria basin. *Ecological Indicators* 145, 109580. doi:10.1016/j.ecolind.2022.109580
- Mugo, R. et al. (2020). Quantifying land use land cover changes in the Lake Victoria Basin using satellite remote sensing: the trends and drivers between 1985 and 2014. *Remote Sensing* 12, 2829. doi:10.3390/rs12172829
- Pietroiusti, R. et al. (2024). Possible role of anthropogenic climate change in the record-breaking 2020 Lake Victoria levels and floods. *Earth System Dynamics* 15, 225–264. doi:10.5194/esd-15-225-2024

**Methods**
- Chini, M., Hostache, R., Giustarini, L., Matgen, P. (2017). A hierarchical split-based approach for parametric thresholding of SAR images: flood inundation as a test case. *IEEE Transactions on Geoscience and Remote Sensing* 55(12), 6975–6988.
- McKee, T.B., Doesken, N.J., Kleist, J. (1993). The relationship of drought frequency and duration to time scales. *8th Conference on Applied Climatology*, Anaheim, CA, 179–184.
- Thom, H.C.S. (1958). A note on the gamma distribution. *Monthly Weather Review* 86, 117–122.

**Data sources**
- Copernicus DEM GLO-30, ESA (2021). Contains modified Copernicus data.
- Copernicus Sentinel-2 L2A, via Google Earth Engine (`COPERNICUS/S2_SR_HARMONIZED`). Contains modified Copernicus Sentinel data [2023–2025].
- Funk, C. et al. (2015). The climate hazards infrared precipitation with stations (CHIRPS). *Scientific Data* 2, 150066. CHIRPS v3.0, UCSB Climate Hazards Center. CC-BY-4.0.
- Funk, C. et al. (2019). A high-resolution 1983–2016 Tmax climate data record based on infrared temperatures and stations (CHIRTS). *Journal of Climate* 32, 5639–5658. CHIRTS-ERA5, UCSB CHC. CC-BY-4.0.
- Giglio, L., Boschetti, L., Roy, D.P., Humber, M.L., Justice, C.O. (2018). The Collection 6 MODIS burned area mapping algorithm and product. *Remote Sensing of Environment* 217, 72–85. MCD64A1 v6.1. <!-- auto:ref -->
- Hansen, M.C. et al. (2013). High-resolution global maps of 21st-century forest cover change. *Science* 342, 850–853. GFC-2025-v1.13. CC-BY-4.0.
- ICPAC Geoportal. Lake Victoria Basin shapefile (`geonode:lv_basin`), 2019.
- Karra, K., Kontgis, C., Statman-Weil, Z., Mazzariello, J.C., Mathis, M., Brumby, S.P. (2021). Global land use / land cover with Sentinel-2 and deep learning. *IGARSS 2021*. Esri/Impact Observatory annual LULC v2. CC BY 4.0. <!-- auto:ref -->
- Lehner, B., Grill, G. (2013). Global river hydrography and network routing. *Hydrological Processes* 27, 2171–2186. HydroRIVERS v1.0.
- Lehner, B., Verdin, K., Jarvis, A. (2008). New global hydrography derived from spaceborne elevation data. *Eos, Transactions, AGU* 89(10), 93–94. HydroSHEDS v1 (https://www.hydrosheds.org). Required attribution (HydroSHEDS licence, Exhibit B): This product MOSAIC Lake Victoria Basin Explorer incorporates data from the HydroSHEDS version 1 database which is © World Wildlife Fund, Inc. (2006-2022) and has been used herein under license. WWF has not evaluated the data as altered and incorporated within MOSAIC Lake Victoria Basin Explorer, and therefore gives no warranty regarding its accuracy, completeness, currency or suitability for any particular purpose. Portions of the HydroSHEDS v1 database incorporate data which are the intellectual property rights of © USGS (2006-2008), NASA (2000-2005), ESRI (1992-1998), CIAT (2004-2006), UNEP-WCMC (1993), WWF (2004), Commonwealth of Australia (2007), and Her Royal Majesty and the British Crown and are used under license. The HydroSHEDS v1 database and more information are available at https://www.hydrosheds.org. HydroSHEDS-derived layers (rivers, sub-catchments) are included for display in this app only and may not be redistributed separately. © World Wildlife Fund, Inc. (2006-2022), used under licence.
- OpenStreetMap contributors (2026). Planet OSM, replication 2026-10-22. https://www.openstreetmap.org/copyright. ODbL 1.0.
- Pekel, J.-F., Cottam, A., Gorelick, N., Belward, A.S. (2016). High-resolution mapping of global surface water and its long-term changes. *Nature* 540, 418–422. JRC Global Surface Water v1.4, monthly history (used only to check the 2020 flood comparison).
- Protomaps (2026). Daily OSM basemap build 2026-10-22, schema v4. https://protomaps.com. Fonts: Noto Sans, SIL Open Font License, via protomaps/basemaps-assets.
- Runfola, D. et al. (2020). geoBoundaries: A global database of political administrative boundaries. *PLoS ONE* 15(4), e0231866. doi:10.1371/journal.pone.0231866. gbOpen ADM1/ADM2; licence per boundary (see §2).
- Salamon, P. et al. (2021). The new, systematic global flood monitoring product of the Copernicus Emergency Management Service. *IGARSS 2021*. doi:10.1109/IGARSS47720.2021.9554214. GFM Product User Manual: https://extwiki.eodc.eu/GFM/PUM. Contains modified Copernicus EMS information [2016–2025].
- Schroeder, W., Oliva, P., Giglio, L., Csiszar, I.A. (2014). The New VIIRS 375 m active fire detection data product. *Remote Sensing of Environment* 143, 85–96. NASA FIRMS VIIRS active fires. <!-- auto:ref -->
- Schwatke, C., Dettmering, D., Bosch, W., Seitz, F. (2015). DAHITI – an innovative approach for estimating water level time series over inland waters using multi-mission satellite altimetry. *Hydrology and Earth System Sciences* 19, 4345–4364. https://dahiti.dgfi.tum.de
- WorldPop (2020). Constrained individual countries 2020, 100 m. University of Southampton. doi:10.5258/SOTON/WP00682. CC-BY-4.0.
- Zanaga, D. et al. (2022). ESA WorldCover 10 m 2021 v200. doi:10.5281/zenodo.7254221. CC BY 4.0. <!-- auto:ref -->
