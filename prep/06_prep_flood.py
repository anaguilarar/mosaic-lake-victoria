"""P0.6 - GFM flood-frequency outputs -> colour-mapped PMTiles + 100 m query COG.

Resampling (never bilinear):
    years_flooded, flood_frequency, max extents: MAX - the 20 m -> z12 warp and every zoomed-out
        level (tiler.max_levels) keep the highest value, so a pixel is coloured if any part of it
        flooded (legend note says so).
    excluded_pct ("Not assessed"): NEAREST warp, MODE overviews - MAX would exaggerate exclusion.
The 100 m query COG takes the MAX of the 20 m cells, and the frontend popover must phrase it as
"flooded in up to N of 10 years within 100 m".

Palettes (colour-blind safe):
    years_flooded 1-10: viridis steps (0 = observed-never-flooded rendered transparent on the map;
                        the legend states this explicitly); 255 nodata transparent.
    flood_frequency:    viridis, stepped 1,2,5,10,20,50,100 %.
    excluded_pct:       transparent below 50, then grey steps ("not mappable by SAR").
    max extents:        single blue (#1f5fbf) for extent=1.
    seasonal frequency: same palette and MAX resampling as flood_frequency; one PMTiles per season
                        (band 1 MAM -> flood_freq_mam, band 2 OND -> flood_freq_ond).

Until the basin run finishes, --placeholder builds a synthetic 3-band raster over the pilot bbox
with the exact band layout, so the frontend can be developed against the real format.

Usage:
    python 06_prep_flood.py                 # real outputs (analysis/flood_frequency/outputs/)
    python 06_prep_flood.py --placeholder
"""
import argparse

import numpy as np
import rasterio
from matplotlib import colormaps
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject

from prep_common import (DATA, FLOOD_COG, FLOOD_MAX, FLOOD_MAXZOOM, FLOOD_SEASONAL, MINZOOM, TILES, WORK, log,
                         setup_logging, update_registry)
from tiler import cut_tiles, make_colormap_encoder, max_levels, warp_to_mercator

QUERY_RES = 100


def viridis_steps(n, lo=0.15, hi=1.0, alpha=230):
    cm = colormaps["viridis"]
    return [tuple(int(c * 255) for c in cm(lo + (hi - lo) * i / max(n - 1, 1))[:3]) + (alpha,) for i in range(n)]


def years_colormap():
    cols = viridis_steps(10)
    cmap = {0: (0, 0, 0, 0)}
    cmap.update({i + 1: cols[i] for i in range(10)})
    return cmap


def freq_colormap():
    steps = [1, 2, 5, 10, 20, 50, 100]
    cols = viridis_steps(len(steps))
    cmap = {0: (0, 0, 0, 0)}
    for v in range(1, 101):
        k = next(i for i, s in enumerate(steps) if v <= s)
        cmap[v] = cols[k]
    return cmap


ZONE_CODE = 254          # band 3: not assessed, look-alike zone (config [masks] zone in analysis/flood_frequency)


def excl_colormap():
    cmap = {v: (0, 0, 0, 0) for v in range(0, 50)}
    for v in range(50, 101):
        g = int(120 - 90 * (v - 50) / 50)
        cmap[v] = (g, g, g, 200)
    cmap[ZONE_CODE] = (30, 30, 30, 200)    # joins "Not assessed" in its darkest grey
    return cmap


def band_vrt(src_path, band):
    """Single-band intermediate GTiff so the tiler sees band 1."""
    out = WORK / f"flood_b{band}_{src_path.stem}.tif"
    if out.exists() and out.stat().st_mtime >= src_path.stat().st_mtime:
        return out
    with rasterio.open(src_path) as s:
        prof = s.profile | dict(count=1, driver="GTiff", tiled=True, blockxsize=512, blockysize=512,
                                compress="DEFLATE")
        with rasterio.open(out, "w", **prof) as d:
            for _, w in s.block_windows(1):
                d.write(s.read(band, window=w), 1, window=w)
    return out


def make_query_cog(src_path):
    """100 m EPSG:32736 COG, MAX of the 20 m cells per band (years, frequency, excluded_pct)."""
    out = DATA / "query" / "flood_query_100m.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(src_path) as s:
        res = QUERY_RES if s.crs.is_projected else QUERY_RES / 111320.0   # ~100 m in degrees
        t, w, h = calculate_default_transform(s.crs, s.crs, s.width, s.height, *s.bounds, resolution=res)
        prof = dict(driver="GTiff", crs=s.crs, transform=t, width=w, height=h, count=s.count,
                    dtype="uint8", nodata=255, tiled=True, blockxsize=256, blockysize=256,
                    compress="DEFLATE")
        with rasterio.open(out, "w", **prof) as d:
            for b in range(1, s.count + 1):
                a = np.full((h, w), 255, "u1")
                reproject(rasterio.band(s, b), a, dst_transform=t, dst_crs=s.crs,
                          src_nodata=255, dst_nodata=255, resampling=Resampling.max)
                d.write(a, b)
                d.set_band_description(b, s.descriptions[b - 1] or f"band{b}")
            d.update_tags(aggregation="max of 20 m cells within 100 m",
                          popover_wording="flooded in up to N of 10 years within 100 m")
    log.info("wrote %s (%.1f MB)", out, out.stat().st_size / 1e6)
    return out


def make_placeholder():
    """Synthetic 3-band uint8 COG over the pilot bbox with the agreed band layout."""
    from rasterio.transform import from_origin
    out = WORK / "flood_placeholder.tif"
    w, h = 700, 400
    t = from_origin(33.9, 0.35, (35.3 - 33.9) / w, (0.35 + 0.45) / h)
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:h, 0:w]
    blob = np.exp(-(((xx - 500) / 90) ** 2 + ((yy - 260) / 50) ** 2))
    years = np.clip(np.round(blob * 9 + rng.random((h, w))), 0, 10).astype("u1")
    freq = np.clip(np.round(blob * 40), 0, 100).astype("u1")
    excl = np.clip(np.round((1 - blob) * 70), 0, 100).astype("u1")
    nod = rng.random((h, w)) < 0.02
    arr = np.stack([years, freq, excl])
    arr[:, nod] = 255
    prof = dict(driver="GTiff", crs="EPSG:4326", transform=t, width=w, height=h, count=3,
                dtype="uint8", nodata=255, tiled=True, blockxsize=256, blockysize=256, compress="DEFLATE")
    with rasterio.open(out, "w", **prof) as d:
        d.write(arr)
        for i, n in enumerate(["years_flooded", "flood_frequency", "excluded_pct"], 1):
            d.set_band_description(i, n)
        d.update_tags(PLACEHOLDER="synthetic data - not real flood information")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--placeholder", action="store_true")
    args = ap.parse_args()
    setup_logging()

    src = make_placeholder() if args.placeholder or not FLOOD_COG.exists() else FLOOD_COG
    placeholder = src.name == "flood_placeholder.tif"
    if placeholder:
        log.warning("building from PLACEHOLDER data (synthetic)")

    def tile(name, single_band, cmap, use_max):
        merc = warp_to_mercator(single_band, name, FLOOD_MAXZOOM,
                                Resampling.max if use_max else Resampling.nearest,
                                dtype="uint8", nodata=255, src_nodata=255,
                                ovr=None if not use_max else Resampling.nearest)
        levels = max_levels(merc, MINZOOM, FLOOD_MAXZOOM) if use_max else None
        cut_tiles(merc, TILES / f"{name}.pmtiles", name, "png", MINZOOM, FLOOD_MAXZOOM,
                  make_colormap_encoder(cmap, 255), Resampling.nearest, levels=levels)

    for name, band, cmap, use_max in [("flood_years", 1, years_colormap(), True),
                                      ("flood_freq", 2, freq_colormap(), True),
                                      ("flood_excl", 3, excl_colormap(), False)]:
        tile(name, band_vrt(src, band), cmap, use_max)

    for key, path in FLOOD_MAX.items():
        if path.exists() and not placeholder:
            tile(key, band_vrt(path, 1), {0: (0, 0, 0, 0), 1: (31, 95, 191, 235)}, True)

    seasonal = {}
    if FLOOD_SEASONAL.exists() and not placeholder:
        for band, season in [(1, "mam"), (2, "ond")]:
            tile(f"flood_freq_{season}", band_vrt(FLOOD_SEASONAL, band), freq_colormap(), True)
            seasonal[f"frequency_{season}"] = f"tiles/flood_freq_{season}.pmtiles"

    q = make_query_cog(src)
    update_registry("flood_hazard", {
        "title": "Flood hazard (observed flood frequency)", "group": "Flood hazard", "type": "raster",
        "placeholder": placeholder,
        "urls": {"years": "tiles/flood_years.pmtiles", "frequency": "tiles/flood_freq.pmtiles",
                 "excluded": "tiles/flood_excl.pmtiles", "query_cog": "query/flood_query_100m.tif",
                 **{k: f"tiles/{k}.pmtiles" for k, p in FLOOD_MAX.items() if (TILES / f"{k}.pmtiles").exists()},
                 **seasonal},
        "minzoom": MINZOOM, "maxzoom": FLOOD_MAXZOOM,
        "tile_aggregation": "max (years, frequency, max extents); mode (excluded)",
        "query": {"aggregation": "max within 100 m",
                  "wording": "flooded in up to {N} of 10 years within 100 m"},
        "palette": {"type": "sequential-cbsafe", "name": "viridis (stepped)"},
        "source": "Copernicus EMS Global Flood Monitoring (Sentinel-1), 20 m, 2016-2025",
        "period": "2016-2025", "units": "band1: years flooded (0-10); band2: % of valid obs; band3: % excluded",
        "licence": "Copernicus EMS: free with attribution",
        "citation": "Salamon et al. (2021) IGARSS, doi:10.1109/IGARSS47720.2021.9554214. "
                    "Contains modified Copernicus EMS information (2016-2025). Hazard proxy, not risk.",
        "caveats": "Flooded vegetation and urban areas under-detected; short floods between overpasses missed; "
                   "band 3 shows where SAR cannot map floods."})


if __name__ == "__main__":
    main()
