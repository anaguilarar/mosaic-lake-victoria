"""Land cover: Esri/Impact Observatory annual LULC v2 (10 m) + ESA WorldCover 2021 reference.

Source: Planetary Computer STAC `io-lulc-annual-v02` (CC BY 4.0), streamed by window from the signed
zone COGs. Probed 2026-10-21: years 2017-2023 only; no 2024 release on PC (stated in the registry).
Processing grid: the shared 30 m basin grid (nearest from the 10 m source - categorical, so nearest/
mode only, as approved). Outputs:
    data/tiles/lulc_YYYY.pmtiles       pre-coloured class tiles per year (z5-12)
    data/tiles/worldcover2021.pmtiles  static reference layer
    data/query/lulc_stack_30m.tif      one band per year, for click queries (class + year)
    data/series/lulc_areas.json        class areas (km2) per year, basin + sub-basins when approved

Usage:  python prep/15_prep_lulc.py
"""
import json
import math

import geopandas as gpd
import numpy as np
import planetary_computer
import pystac_client
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject

from prep_common import (BASIN_GPKG, BASIN_LAYER, BBOX, DATA, MOSAIC, SERIES, TILES, WORK, log,
                         setup_logging, update_registry)
from tiler import cut_tiles, make_colormap_encoder, warp_to_mercator

PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
YEARS = range(2017, 2024)
RES = 1 / 3600.0                                    # ~30 m processing grid (display z<=12)
NODATA = 0

# Impact Observatory 9-class scheme (v2 values) with its published colours
IO_CLASSES = {
    1: ("Water", (65, 155, 223)), 2: ("Trees", (57, 125, 73)), 4: ("Flooded vegetation", (122, 135, 198)),
    5: ("Crops", (228, 150, 53)), 7: ("Built area", (196, 40, 27)), 8: ("Bare ground", (165, 155, 143)),
    9: ("Snow/ice", (168, 235, 255)), 10: ("Clouds", (97, 97, 97)), 11: ("Rangeland", (227, 226, 195)),
}
WC_CLASSES = {10: ("Tree cover", (0, 100, 0)), 20: ("Shrubland", (255, 187, 34)),
              30: ("Grassland", (255, 255, 76)), 40: ("Cropland", (240, 150, 255)),
              50: ("Built-up", (250, 0, 0)), 60: ("Bare/sparse", (180, 180, 180)),
              80: ("Water", (0, 100, 200)), 90: ("Wetland", (0, 150, 160)),
              95: ("Mangroves", (0, 207, 117)), 100: ("Moss/lichen", (250, 230, 160))}
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{tile}_Map.tif")


def grid():
    w, s, e, n = BBOX
    width, height = math.ceil((e - w) / RES), math.ceil((n - s) / RES)
    return from_origin(w, n, RES, RES), width, height


def mosaic_items(hrefs, t, width, height):
    import time as _time
    env = rasterio.Env(GDAL_HTTP_MAX_RETRY=8, GDAL_HTTP_RETRY_DELAY=10,
                       GDAL_HTTP_TIMEOUT=300, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR")
    out = np.zeros((height, width), "u1")
    for href in hrefs:
        for attempt in range(4):
            if attempt:
                try:                              # signed tokens expire: re-sign on retry
                    href = planetary_computer.sign(href.split("?")[0])
                except Exception:
                    pass
            try:
                with env, rasterio.open(href) as src:
                    tmp = np.zeros((height, width), "u1")
                    reproject(rasterio.band(src, 1), tmp, dst_transform=t, dst_crs="EPSG:4326",
                              dst_nodata=0, resampling=Resampling.nearest, num_threads=4)
                    out = np.where(tmp > 0, tmp, out)
                break
            except Exception as e:              # transient https / expired-token failures
                log.warning("reproject attempt %d failed (%s) for %s", attempt + 1,
                            type(e).__name__, href.split("?")[0][-50:])
                _time.sleep(20 * (attempt + 1))
        else:
            raise RuntimeError("COG unreadable after retries: " + href.split("?")[0][-60:])
    return out


def year_tiles(name, arr, t, cmap, maxzoom=12):
    prof = dict(driver="GTiff", crs="EPSG:4326", transform=t, width=arr.shape[1], height=arr.shape[0],
                count=1, dtype="uint8", nodata=None, tiled=True, blockxsize=512, blockysize=512,
                compress="DEFLATE", BIGTIFF="IF_SAFER")
    f = WORK / f"{name}_clip.tif"
    with rasterio.open(f, "w", **prof) as d:
        d.write(arr, 1)
    merc = warp_to_mercator(f, name, maxzoom, Resampling.nearest, dtype="uint8")   # 0 is data
    cut_tiles(merc, TILES / f"{name}.pmtiles", name, "png", 5, maxzoom,
              make_colormap_encoder(cmap, 0), Resampling.nearest)


def main():
    setup_logging()
    client = pystac_client.Client.open(PC, modifier=planetary_computer.sign_inplace)
    t, width, height = grid()
    cmap = {v: c + (255,) for v, (_, c) in IO_CLASSES.items()}
    basin = gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()
    bmask = geometry_mask([basin], out_shape=(height, width), transform=t, invert=True)
    sub = MOSAIC / "analysis" / "flood_frequency" / "inputs" / "subbasins.gpkg"
    regions = {"Lake Victoria Basin": bmask}
    if sub.exists():
        for r in gpd.read_file(sub, layer="subbasins").itertuples():
            regions[r.name] = geometry_mask([r.geometry], out_shape=(height, width), transform=t, invert=True) & bmask

    lat_c = t.f + t.e * (np.arange(height) + 0.5)
    px_km2 = (RES * 111.32) * (RES * 110.57) * np.cos(np.radians(lat_c))
    areas = {str(y): {} for y in YEARS}
    stack = []
    for y in YEARS:
        cache = WORK / f"lulc_{y}_clip.tif"
        if cache.exists():                       # resume: mosaic cached by a previous run
            with rasterio.open(cache) as cs:
                arr = cs.read(1)
            log.info("%d: from cache", y)
        else:
            s = client.search(collections=["io-lulc-annual-v02"], bbox=list(BBOX),
                              datetime=f"{y}-01-01/{y}-12-31", max_items=50)
            hrefs = [it.assets["data"].href for it in s.items()]
            log.info("%d: %d zone COGs", y, len(hrefs))
            arr = mosaic_items(hrefs, t, width, height)
        arr = np.where(bmask, arr, 0)
        stack.append(arr)
        if not (TILES / f"lulc_{y}.pmtiles").exists():
            year_tiles(f"lulc_{y}", arr, t, cmap)
        for name, m in regions.items():
            d = {}
            vals, counts = np.unique(arr[m], return_counts=True)
            rows_per_val = {}
            for v in vals:
                if v == 0:
                    continue
                rows = ((arr == v) & m).sum(1)
                d[IO_CLASSES.get(int(v), (str(v),))[0]] = round(float((rows * px_km2).sum()), 1)
            areas[str(y)].setdefault(name, d)
        log.info("%d done; basin crops km2: %s", y, areas[str(y)]["Lake Victoria Basin"].get("Crops"))

    q = DATA / "query" / "lulc_stack_30m.tif"
    q.parent.mkdir(parents=True, exist_ok=True)
    prof = dict(driver="GTiff", crs="EPSG:4326", transform=t, width=width, height=height,
                count=len(stack), dtype="uint8", nodata=0, tiled=True, blockxsize=256, blockysize=256,
                compress="DEFLATE", BIGTIFF="IF_SAFER")
    with rasterio.open(q, "w", **prof) as d:
        for i, (yy, a) in enumerate(zip(YEARS, stack), 1):
            d.write(np.where(bmask, a, 0), i)
            d.set_band_description(i, str(yy))
        d.update_tags(classes=json.dumps({v: n for v, (n, _) in IO_CLASSES.items()}))
    log.info("lulc_stack_30m.tif: %.0f MB", q.stat().st_size / 1e6)

    (SERIES / "lulc_areas.json").write_text(json.dumps(
        {"units": "km2", "years": [str(y) for y in YEARS], "regions_note":
         "sub-basins join after approval", "areas": areas,
         "caveat": "Global land-cover products disagree on cropland in sub-Saharan Africa "
                   "(Kerner et al. 2023); year-to-year change is indicative."}), encoding="utf-8")

    # WorldCover 2021 static reference
    wdir = WORK / "worldcover"
    wdir.mkdir(parents=True, exist_ok=True)
    tiles = [f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
             for lat in range(-6, 3, 3) for lon in range(27, 36, 3)]
    files = []
    for tl in tiles:
        dest = wdir / f"wc_{tl}.tif"
        if not dest.exists():
            r = requests.get(WORLDCOVER_URL.format(tile=tl), stream=True, timeout=1200)
            if r.status_code != 200:
                continue
            with open(dest, "wb") as fh:
                for ch in r.iter_content(1 << 22):
                    fh.write(ch)
            log.info("worldcover %s: %.0f MB", tl, dest.stat().st_size / 1e6)
        files.append(dest)
    if not (TILES / "worldcover2021.pmtiles").exists():
        wc = mosaic_items([str(f) for f in files], t, width, height)
        year_tiles("worldcover2021", np.where(bmask, wc, 0), t,
                   {v: c + (255,) for v, (_, c) in WC_CLASSES.items()})

    update_registry("landcover", {
        "title": "Land cover (Esri/IO annual)", "group": "Land", "type": "lulc",
        "urls": {"tiles": {str(y): f"tiles/lulc_{y}.pmtiles" for y in YEARS},
                 "query_cog": "query/lulc_stack_30m.tif", "areas": "series/lulc_areas.json",
                 "worldcover": "tiles/worldcover2021.pmtiles"},
        "years": list(YEARS), "classes": {v: {"name": n, "rgb": c} for v, (n, c) in IO_CLASSES.items()},
        "minzoom": 5, "maxzoom": 12,
        "source": "Esri/Impact Observatory annual LULC v2 (10 m; displayed at 30 m, nearest), "
                  "via Microsoft Planetary Computer (io-lulc-annual-v02)",
        "period": "2017-2023 (no 2024 release on Planetary Computer at build time, probed 2026-10-21)",
        "units": "land-cover class", "licence": "CC BY 4.0",
        "caveats": "Global land-cover products disagree on cropland in sub-Saharan Africa "
                   "(Kerner et al. 2023); year-to-year change is indicative.",
        "citation": "Karra et al. (2021), IGARSS; Impact Observatory, Esri, Microsoft."})
    update_registry("worldcover", {
        "title": "Land cover reference (ESA WorldCover 2021)", "group": "Land", "type": "raster",
        "urls": {"pmtiles": "tiles/worldcover2021.pmtiles"},
        "classes": {v: {"name": n, "rgb": c} for v, (n, c) in WC_CLASSES.items()},
        "minzoom": 5, "maxzoom": 12,
        "source": "ESA WorldCover 10 m 2021 v200 (displayed at 30 m, nearest)", "period": "2021",
        "units": "land-cover class", "licence": "CC BY 4.0",
        "citation": "Zanaga et al. (2022). ESA WorldCover 10 m 2021 v200. doi:10.5281/zenodo.7254221"})


if __name__ == "__main__":
    main()
