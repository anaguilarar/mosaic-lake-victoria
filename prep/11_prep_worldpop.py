"""WorldPop constrained 100 m population: mosaic for the basin bbox + display tiles + exposure input.

Release policy (approved): probe for a constrained release newer than the 2020 "Global 2000-2020
Constrained" product via the WorldPop REST API; if none is found, use 2020 and say so in the registry.

Outputs:
    data/query/pop_100m.tif          float32 COG (persons per ~100 m cell), basin bbox - click queries
    data/tiles/population.pmtiles    log-scaled OrRd raster tiles z5-12 (0 = transparent)
    registry entry "population" (labelled exposure input)

Usage:  python prep/11_prep_worldpop.py
"""
import math

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import reproject

from prep_common import BBOX, DATA, TILES, WORK, log, setup_logging, update_registry
from tiler import cut_tiles, make_colormap_encoder, warp_to_mercator

ISO = ["KEN", "UGA", "TZA", "RWA", "BDI"]
FALLBACK_2020 = ("https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/"
                 "BSGM/{ISO}/{iso}_ppp_2020_constrained.tif")
FALLBACK_2020_MAXAR = ("https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/"
                       "maxar_v1/{ISO}/{iso}_ppp_2020_constrained.tif")
RES = 1 / 1200.0                                   # 3 arc-sec


def probe_release():
    """Look for a constrained release newer than 2020 via the WorldPop REST catalogue."""
    try:
        r = requests.get("https://hub.worldpop.org/rest/data/pop", timeout=60)
        aliases = [d.get("alias", "") for d in r.json().get("data", [])]
        newer = [a for a in aliases if "constrained" in a.lower() and any(str(y) in a for y in range(2021, 2031))]
        log.info("constrained aliases on hub: %s", [a for a in aliases if "onstrained" in a] or "none listed")
        if newer:
            return newer
    except Exception as e:
        log.warning("hub.worldpop.org probe failed (%s); falling back to the 2020 release", e)
    return []


def download_country(iso):
    dest = WORK / "worldpop" / f"{iso.lower()}_constrained.tif"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    for pattern in (FALLBACK_2020, FALLBACK_2020_MAXAR):
        url = pattern.format(ISO=iso, iso=iso.lower())
        try:
            with requests.get(url, stream=True, timeout=1200) as r:
                if r.status_code != 200:
                    continue
                with open(dest.with_suffix(".part"), "wb") as f:
                    for chunk in r.iter_content(1 << 22):
                        f.write(chunk)
            dest.with_suffix(".part").replace(dest)
            log.info("%s: %.0f MB (%s)", iso, dest.stat().st_size / 1e6, url.split("/")[-3])
            return dest
        except requests.RequestException as e:
            log.warning("%s: %s failed (%s)", iso, url, e)
    raise SystemExit(f"could not download WorldPop for {iso}")


def main():
    setup_logging()
    newer = probe_release()
    release_note = ("2020 constrained (Global 2000-2020, BSGM/maxar): no newer constrained release was "
                    "found on hub.worldpop.org at build time" if not newer else f"NEWER RELEASE FOUND: {newer}")
    log.info("release decision: %s", release_note)
    if newer:
        log.warning("a newer constrained release appears to exist (%s); this script still uses 2020 - "
                    "extend download_country() for the new path and re-run", newer)

    files = [download_country(i) for i in ISO]

    w, s, e, n = BBOX
    width = math.ceil((e - w) / RES)
    height = math.ceil((n - s) / RES)
    t = from_origin(w, n, RES, RES)
    mosaic = np.zeros((height, width), "f4")
    for f in files:
        with rasterio.open(f) as src:
            tmp = np.full((height, width), np.nan, "f4")
            reproject(rasterio.band(src, 1), tmp, dst_transform=t, dst_crs="EPSG:4326",
                      src_nodata=src.nodata, dst_nodata=np.nan, resampling=Resampling.nearest)
            m = np.isfinite(tmp)
            mosaic[m] = tmp[m]                      # countries do not overlap except at borders
    out = DATA / "query" / "pop_100m.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    prof = dict(driver="GTiff", height=height, width=width, count=1, dtype="float32", crs="EPSG:4326",
                transform=t, nodata=-1, tiled=True, blockxsize=512, blockysize=512,
                compress="DEFLATE", predictor=2, BIGTIFF="IF_SAFER")
    mosaic = np.where(np.isfinite(mosaic), mosaic, -1).astype("f4")
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(mosaic, 1)
        dst.build_overviews([2, 4, 8, 16, 32], Resampling.average)
        dst.update_tags(units="persons per ~100 m grid cell", release=release_note)
    tot = float(mosaic[mosaic > 0].sum())
    log.info("pop_100m.tif: %dx%d, basin-bbox total %.1f M people, %.0f MB",
             width, height, tot / 1e6, out.stat().st_size / 1e6)

    # display tiles: log10 scale into a 1..200 uint8 code, OrRd ramp, 0/nodata transparent
    code = np.zeros_like(mosaic, "f4")
    pos = mosaic > 0.5
    code[pos] = np.clip(1 + 199 * np.log10(np.clip(mosaic[pos], 1, 3000)) / np.log10(3000), 1, 200)
    enc = WORK / "pop_code.tif"
    with rasterio.open(enc, "w", **{**prof, "dtype": "uint8", "nodata": 0}) as dst:
        dst.write(code.astype("u1"), 1)
    ORRD = ["#fff3e5", "#fdd49e", "#fdbb84", "#fc8d59", "#ef6548", "#d7301f", "#b30000", "#7f0000"]
    cmap = {}
    for v in range(1, 201):
        f = (v - 1) / 199 * (len(ORRD) - 1)
        i = int(f); frac = f - i
        h = lambda c: [int(c[k:k+2], 16) for k in (1, 3, 5)]
        a, b = h(ORRD[i]), h(ORRD[min(i + 1, len(ORRD) - 1)])
        cmap[v] = tuple(int(a[k] + (b[k] - a[k]) * frac) for k in range(3)) + (215,)
    merc = warp_to_mercator(enc, "pop", 12, Resampling.nearest, dtype="uint8",
                            ovr=Resampling.average)   # counts: average overviews keep sparse settlements visible
    cut_tiles(merc, TILES / "population.pmtiles", "WorldPop 2020 constrained", "png", 5, 12,
              make_colormap_encoder(cmap, 0), Resampling.nearest)

    update_registry("population", {
        "title": "Population (exposure input)", "group": "Exposure", "type": "raster",
        "urls": {"pmtiles": "tiles/population.pmtiles", "query_cog": "query/pop_100m.tif"},
        "minzoom": 5, "maxzoom": 12,
        "legend": {"scale": "log", "min": 1, "max": 3000, "units": "persons per ~100 m cell"},
        "source": "WorldPop constrained individual countries 2020, 100 m (KEN, UGA, TZA, RWA, BDI)",
        "release_note": release_note,
        "period": "2020", "units": "persons per ~100 m grid cell", "licence": "CC-BY-4.0",
        "caveats": "Exposure input (people in place), not risk; census-era modelled counts.",
        "citation": "WorldPop (2020), School of Geography and Environmental Science, University of "
                    "Southampton. doi:10.5258/SOTON/WP00682"})


if __name__ == "__main__":
    main()
