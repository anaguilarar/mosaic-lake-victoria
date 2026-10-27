"""Hansen Global Forest Change: tree-cover loss year + tree cover 2000, for the basin bbox only.

Approved rules: download only the granules covering the bbox; threshold tree cover 2000 >= 30 %
(stated in the panel); label "tree-cover loss", never deforestation; note that detection improved
around 2011-2013 (Landsat 8), so annual values are not strictly comparable across that break.
The newest available GFC release is auto-detected (version candidates probed) and recorded.

Outputs:
    data/tiles/forest_loss.pmtiles    loss YEAR encoded in the red channel (value = year-2000),
                                      styled cumulatively in the app via raster-color (or static fallback)
    data/tiles/treecover2000.pmtiles  green ramp where cover >= 30 %
    data/query/forest_loss_30m... not kept (too big); per-year areas instead:
    data/series/forest_loss.json      annual tree-cover-loss area (km2), basin (+ sub-basins when approved)

Usage:  python prep/12_prep_hansen.py
        python prep/12_prep_hansen.py --series-only   # recompute forest_loss.json (e.g. after the sub-basins
                                                      # are approved) from the saved clip; no download, no tiles
"""
import json
import math

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

from prep_common import (BASIN_GPKG, BASIN_LAYER, BBOX, MOSAIC, SERIES, TILES, WORK, log,
                         setup_logging, update_registry)
from tiler import cut_tiles, make_colormap_encoder, warp_to_mercator

BASE = "https://storage.googleapis.com/earthenginepartners-hansen/{ver}/Hansen_{ver}_{layer}_{gran}.tif"
VERSIONS = ["GFC-2025-v1.13", "GFC-2024-v1.12", "GFC-2023-v1.11"]      # newest first
LAYERS = ["lossyear", "treecover2000"]
RES = 1 / 4000.0                                   # ~0.00025 deg = 30 m-ish (native 0.00025)
COVER_MIN = 30


def granules(bbox):
    w, s, e, n = bbox
    gs = set()
    for lon in range(math.floor(w / 10) * 10, math.ceil(e / 10) * 10, 10):
        for lat in range(math.floor(s / 10) * 10 + 10, math.ceil(n / 10) * 10 + 10, 10):
            gs.add(f"{abs(lat):02d}{'N' if lat >= 0 else 'S'}_{abs(lon):03d}{'E' if lon >= 0 else 'W'}")
    return sorted(gs)


def pick_version():
    g = granules(BBOX)[0]
    for v in VERSIONS:
        url = BASE.format(ver=v, layer="lossyear", gran=g)
        if requests.head(url, timeout=60).status_code == 200:
            log.info("using %s", v)
            return v
    raise SystemExit("no GFC version found among " + ", ".join(VERSIONS))


def download(ver, layer, gran):
    dest = WORK / "hansen" / f"{ver}_{layer}_{gran}.tif"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = BASE.format(ver=ver, layer=layer, gran=gran)
    log.info("downloading %s %s %s", ver, layer, gran)
    with requests.get(url, stream=True, timeout=3600) as r:
        r.raise_for_status()
        with open(dest.with_suffix(".part"), "wb") as f:
            for chunk in r.iter_content(1 << 22):
                f.write(chunk)
    dest.with_suffix(".part").replace(dest)
    log.info("  %.0f MB", dest.stat().st_size / 1e6)
    return dest


def mosaic_layer(ver, layer):
    w, s, e, n = BBOX
    width, height = math.ceil((e - w) / RES), math.ceil((n - s) / RES)
    t = from_origin(w, n, RES, RES)
    out = np.zeros((height, width), "u1")
    for g in granules(BBOX):
        f = download(ver, layer, g)
        with rasterio.open(f) as src:
            tmp = np.zeros((height, width), "u1")
            reproject(rasterio.band(src, 1), tmp, dst_transform=t, dst_crs="EPSG:4326",
                      dst_nodata=0, resampling=Resampling.nearest)
            out = np.maximum(out, tmp)
    return out, t


def series_only():
    """Recompute data/series/forest_loss.json from the saved clip (keeps the recorded GFC version)."""
    old = json.loads((SERIES / "forest_loss.json").read_text(encoding="utf-8"))
    with rasterio.open(WORK / "hansen_loss_clip.tif") as src:
        loss, t = src.read(1), src.transform
    write_series(loss, t, old["version"], int(old["version"].split("-")[1]))


def write_series(loss, t, ver, max_year):
    # annual loss areas (km2), basin and sub-basins when approved
    import geopandas as gpd
    from rasterio.features import geometry_mask
    lat_centres = t.f + t.e * (np.arange(loss.shape[0]) + 0.5)
    px_km2 = (RES * 111.32) * (RES * 110.57) * np.cos(np.radians(lat_centres))          # per row
    regions = {"Lake Victoria Basin": gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()}
    sub = MOSAIC / "analysis" / "flood_frequency" / "inputs" / "subbasins.gpkg"
    if sub.exists():
        for r in gpd.read_file(sub, layer="subbasins").to_crs("EPSG:4326").itertuples():
            regions[r.name] = r.geometry
    series = {"version": ver, "cover_threshold_pct": COVER_MIN, "units": "km2/year",
              "note": "tree-cover loss (not deforestation); detection improved ~2011-2013 (Landsat 8), "
                      "annual values are not strictly comparable across that break",
              "regions": {}}
    for name, geom in regions.items():
        m = ~geometry_mask([geom], out_shape=loss.shape, transform=t, invert=False, all_touched=False)
        yearly = {}
        for y in range(1, max_year - 2000 + 1):
            rows = ((loss == y) & m).sum(1)
            yearly[str(2000 + y)] = round(float((rows * px_km2).sum()), 2)
        series["regions"][name] = yearly
        log.info("%s: total loss 2001-%d = %.0f km2", name, max_year, sum(yearly.values()))
    (SERIES / "forest_loss.json").write_text(json.dumps(series), encoding="utf-8")


def main():
    setup_logging()
    import sys
    if "--series-only" in sys.argv:
        return series_only()
    ver = pick_version()
    max_year = int(ver.split("-")[1])                   # e.g. GFC-2024-v1.12 -> loss through 2024
    loss, t = mosaic_layer(ver, "lossyear")             # 0 none, 1..N = 2001..max_year
    cover, _ = mosaic_layer(ver, "treecover2000")       # percent

    covered = cover >= COVER_MIN
    loss = np.where(covered, loss, 0).astype("u1")      # loss restricted to >=30 % cover in 2000
    log.info("loss pixels (cover >= %d%%): %d", COVER_MIN, int((loss > 0).sum()))

    prof = dict(driver="GTiff", crs="EPSG:4326", transform=t, width=loss.shape[1], height=loss.shape[0],
                count=1, dtype="uint8", nodata=0, tiled=True, blockxsize=512, blockysize=512,
                compress="DEFLATE", BIGTIFF="IF_SAFER")
    lf = WORK / "hansen_loss_clip.tif"
    with rasterio.open(lf, "w", **prof) as d:
        d.write(loss, 1)
    cf = WORK / "hansen_cover_clip.tif"
    with rasterio.open(cf, "w", **prof) as d:
        d.write(np.where(covered, cover, 0).astype("u1"), 1)

    # loss tiles: the YEAR value itself in the red channel (styled cumulatively client-side)
    merc = warp_to_mercator(lf, "forestloss", 12, Resampling.nearest, dtype="uint8")  # 0 is DATA
    year_cmap = {v: (v, 0, 0, 255) for v in range(1, max_year - 2000 + 1)}
    cut_tiles(merc, TILES / "forest_loss.pmtiles", "GFC loss year", "png", 5, 12,
              make_colormap_encoder(year_cmap, 0), Resampling.nearest)

    GREENS = {v: None for v in range(0, 101)}
    cmap = {}
    for v in range(COVER_MIN, 101):
        f = (v - COVER_MIN) / (100 - COVER_MIN)
        cmap[v] = (int(199 - 150 * f), int(228 - 124 * f), int(192 - 148 * f), 200)   # #c7e4c0 -> #316844
    merc2 = warp_to_mercator(cf, "treecover", 12, Resampling.nearest, dtype="uint8")  # 0 is DATA
    cut_tiles(merc2, TILES / "treecover2000.pmtiles", "Tree cover 2000", "png", 5, 12,
              make_colormap_encoder(cmap, 0), Resampling.nearest)

    write_series(loss, t, ver, max_year)

    update_registry("forest_loss", {
        "title": "Tree-cover loss (Hansen GFC)", "group": "Land", "type": "forest",
        "urls": {"loss": "tiles/forest_loss.pmtiles", "cover": "tiles/treecover2000.pmtiles",
                 "series": "series/forest_loss.json"},
        "minzoom": 5, "maxzoom": 12, "max_year": max_year,
        "source": f"Hansen Global Forest Change {ver}; loss where tree cover 2000 >= {COVER_MIN} %",
        "period": f"2001-{max_year}", "units": "loss year; cover %", "licence": "CC-BY-4.0",
        "caveats": f"Tree-cover loss, not deforestation; only where cover 2000 >= {COVER_MIN} %; "
                   "detection improved ~2011-2013, annual values not strictly comparable across the break.",
        "citation": "Hansen et al. (2013), Science 342:850-853. Data: UMD/Google/USGS/NASA."})


if __name__ == "__main__":
    main()
