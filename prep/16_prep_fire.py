"""Fire: NASA FIRMS VIIRS active fires (archive CSVs) + MODIS MCD64A1 v6.1 burned area.

Approved rules: the fire-density time series uses VIIRS S-NPP only (2012-2025) for consistency;
NOAA-20 (archive starts 2020) appears only in the point layer, noted in the panel. Confidence
nominal/high only. Burned area: annual burned mask per ~500 m cell from MCD64A1 Burn_Date (>0),
via Planetary Computer.

Outputs:
    data/tiles/fire_density_YYYY.pmtiles   S-NPP fires per km2 on a ~1 km grid, per year (z5-10)
    data/fire/points_YYYY.geojson          S-NPP + NOAA-20 detections (conf n/h), for zoom >= 10
    data/tiles/burned_YYYY.pmtiles         MCD64A1 annual burned cells (z5-10)
    data/series/fire.json                  annual counts and burned km2, basin (+ sub-basins later)

Usage:  python prep/16_prep_fire.py [--skip-modis] [--skip-firms]
"""
import argparse
import io
import json
import math

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.warp import reproject

from prep_common import (BASIN_GPKG, BASIN_LAYER, BBOX, DATA, SERIES, TILES, WORK, log,
                         setup_logging, update_registry)
from tiler import cut_tiles, make_colormap_encoder, warp_to_mercator

FIRMS = "https://firms.modaps.eosdis.nasa.gov/data/country/{product}/{year}/{product}_{year}_{country}.csv"
COUNTRIES = ["Kenya", "Uganda", "United_Republic_of_Tanzania", "Rwanda", "Burundi"]
SNPP_YEARS = range(2012, 2026)
J1_YEARS = range(2020, 2026)
J1_PRODUCT = "viirs-jpss1"                          # FIRMS archive name for NOAA-20
DENS_RES = 0.01                                     # ~1.1 km
BURN_RES = 0.005                                    # ~550 m
MAGMA7 = ["#1e1049", "#50127b", "#842681", "#b73779", "#e55064", "#fb8761", "#fec287"]


def fetch_csv(product, year, country):
    dest = WORK / "firms" / f"{product}_{year}_{country}.csv"
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = FIRMS.format(product=product, year=year, country=country)
    r = requests.get(url, timeout=1800)
    if r.status_code != 200 or not r.content.startswith(b"latitude"):
        log.warning("no archive: %s (%s)", url.split('/data/')[1], r.status_code)
        dest.write_bytes(b"")
        return dest
    dest.write_bytes(r.content)
    log.info("%s %s %s: %.1f MB", product, year, country, len(r.content) / 1e6)
    return dest


def load_fires(product, years):
    frames = []
    w, s, e, n = BBOX
    for y in years:
        for c in COUNTRIES:
            f = fetch_csv(product, y, c)
            if f.stat().st_size == 0:
                continue
            d = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "confidence", "frp"])
            d = d[(d.longitude >= w) & (d.longitude <= e) & (d.latitude >= s) & (d.latitude <= n)]
            d = d[d.confidence.astype(str).str.lower().isin(["n", "h", "nominal", "high"])]
            d["year"] = y
            frames.append(d)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    log.info("%s: %d detections (conf n/h, bbox)", product, len(out))
    return out


def density_tiles(d, grid_t, width, height, px_km2):
    steps = [0.1, 0.5, 1, 2, 5, 10, 1e9]
    cmap = {}
    for code in range(1, 201):
        v = code / 10.0
        k = next(i for i, sx in enumerate(steps) if v <= sx)
        h = MAGMA7[min(k, 6)]
        cmap[code] = tuple(int(h[i:i+2], 16) for i in (1, 3, 5)) + (220,)
    for y, g in d.groupby("year"):
        y = int(y)
        if (TILES / f"fire_density_{y}.pmtiles").exists():
            continue
        hist, _, _ = np.histogram2d(g.latitude, g.longitude,
                                    bins=[height, width],
                                    range=[[BBOX[1], BBOX[3]], [BBOX[0], BBOX[2]]])
        dens = np.flipud(hist) / px_km2[:, None]
        code = np.clip(np.round(dens * 10), 0, 200).astype("u1")
        f = WORK / f"fire_density_{y}.tif"
        prof = dict(driver="GTiff", crs="EPSG:4326", transform=grid_t, width=width, height=height,
                    count=1, dtype="uint8", tiled=True, compress="DEFLATE")
        with rasterio.open(f, "w", **prof) as dst:
            dst.write(code, 1)
        merc = warp_to_mercator(f, f"fire_density_{y}", 10, Resampling.nearest, dtype="uint8")
        cut_tiles(merc, TILES / f"fire_density_{y}.pmtiles", f"fire density {y}", "png", 5, 10,
                  make_colormap_encoder(cmap, 0), Resampling.nearest)


def write_points(snpp, j1):
    out = DATA / "fire"
    out.mkdir(parents=True, exist_ok=True)
    allpts = pd.concat([snpp.assign(sensor="S-NPP"), j1.assign(sensor="NOAA-20")], ignore_index=True)
    for y, g in allpts.groupby("year"):
        y = int(y)
        feats = [{"type": "Feature", "geometry": {"type": "Point",
                  "coordinates": [round(r.longitude, 4), round(r.latitude, 4)]},
                  "properties": {"d": r.acq_date, "s": r.sensor, "frp": round(float(r.frp), 1)}}
                 for r in g.itertuples()]
        (out / f"points_{y}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")
    log.info("point files: %d years", allpts.year.nunique())
    return allpts


def modis_burned(basin_mask, grid_t, width, height, px_km2):
    import planetary_computer
    import pystac_client
    client = pystac_client.Client.open("https://planetarycomputer.microsoft.com/api/stac/v1",
                                       modifier=planetary_computer.sign_inplace)
    burned_km2 = {}
    cmap = {1: (120, 32, 18, 230)}
    for y in range(2001, 2026):
        f = WORK / f"burned_{y}.tif"
        if not (TILES / f"burned_{y}.pmtiles").exists():
            try:
                s = client.search(collections=["modis-64A1-061"], bbox=list(BBOX),
                                  datetime=f"{y}-01-01/{y}-12-31", max_items=40)
                items = list(s.items())
                burned = np.zeros((height, width), "u1")
                n_items = 0
                for it in items:
                    with rasterio.open(it.assets["Burn_Date"].href) as src:
                        tmp = np.zeros((height, width), "i2")
                        reproject(rasterio.band(src, 1), tmp, dst_transform=grid_t, dst_crs="EPSG:4326",
                                  dst_nodata=0, resampling=Resampling.nearest, num_threads=4)
                        burned |= (tmp > 0).astype("u1")
                    n_items += 1
            except Exception as e:
                log.error("MCD64A1 %d failed (%s: %s) - skipping year", y, type(e).__name__, str(e)[:150])
                continue
            prof = dict(driver="GTiff", crs="EPSG:4326", transform=grid_t, width=width, height=height,
                        count=1, dtype="uint8", tiled=True, compress="DEFLATE")
            with rasterio.open(f, "w", **prof) as dst:
                dst.write(burned, 1)
            merc = warp_to_mercator(f, f"burned_{y}", 10, Resampling.nearest, dtype="uint8")
            cut_tiles(merc, TILES / f"burned_{y}.pmtiles", f"burned area {y}", "png", 5, 10,
                      make_colormap_encoder(cmap, 0), Resampling.nearest)
            log.info("MCD64A1 %d: %d items", y, n_items)
        with rasterio.open(f) as src:
            b = src.read(1).astype(bool) & basin_mask
        burned_km2[str(y)] = round(float((b.sum(1) * px_km2).sum()), 1)
        log.info("burned %d: %.0f km2", y, burned_km2[str(y)])
    return burned_km2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-modis", action="store_true")
    ap.add_argument("--skip-firms", action="store_true")
    args = ap.parse_args()
    setup_logging()

    w, s, e, n = BBOX
    dw, dh = math.ceil((e - w) / DENS_RES), math.ceil((n - s) / DENS_RES)
    dt = from_origin(w, n, DENS_RES, DENS_RES)
    dlat = n - DENS_RES * (np.arange(dh) + 0.5)
    dpx_km2 = (DENS_RES * 111.32) * (DENS_RES * 110.57) * np.cos(np.radians(dlat))

    basin = gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()
    counts = {}
    if not args.skip_firms:
        snpp = load_fires("viirs-snpp", SNPP_YEARS)
        j1 = load_fires(J1_PRODUCT, J1_YEARS)
        density_tiles(snpp, dt, dw, dh, dpx_km2)
        allpts = write_points(snpp, j1)
        gmask = gpd.GeoSeries(gpd.points_from_xy(snpp.longitude, snpp.latitude), crs="EPSG:4326")
        inb = gmask.within(basin).values
        counts = snpp[inb].groupby("year").size().astype(int).to_dict()
        counts = {str(k): int(v) for k, v in counts.items()}

    bw, bh = math.ceil((e - w) / BURN_RES), math.ceil((n - s) / BURN_RES)
    bt = from_origin(w, n, BURN_RES, BURN_RES)
    blat = n - BURN_RES * (np.arange(bh) + 0.5)
    bpx_km2 = (BURN_RES * 111.32) * (BURN_RES * 110.57) * np.cos(np.radians(blat))
    bmask = geometry_mask([basin], out_shape=(bh, bw), transform=bt, invert=True)
    burned = {} if args.skip_modis else modis_burned(bmask, bt, bw, bh, bpx_km2)

    (SERIES / "fire.json").write_text(json.dumps({
        "snpp_detections_basin": counts, "burned_km2_basin": burned,
        "density_note": "density series uses VIIRS S-NPP only (2012-2025) for cross-year consistency; "
                        "NOAA-20 (from 2020) appears only in the point layer",
        "caveats": "active fires are mostly savanna and crop-residue burning; charcoal production is "
                   "not detected reliably; cloud cover hides wet-season fires"}), encoding="utf-8")

    update_registry("fire", {
        "title": "Active fires (VIIRS)", "group": "Fire", "type": "fire",
        "urls": {"density": {str(y): f"tiles/fire_density_{y}.pmtiles" for y in SNPP_YEARS},
                 "points": {str(y): f"fire/points_{y}.geojson" for y in SNPP_YEARS},
                 "series": "series/fire.json"},
        "years": list(SNPP_YEARS), "minzoom": 5, "maxzoom": 10, "points_from_zoom": 10,
        "legend_steps": {"colors": MAGMA7[:6], "breaks": [0.1, 0.5, 1, 2, 5, 10], "units": "fires/km2/yr"},
        "source": "NASA FIRMS VIIRS 375 m active fires; density: S-NPP only (2012-2025); "
                  "points: S-NPP + NOAA-20 (NOAA-20 archive from 2020); confidence nominal/high",
        "period": "2012-2025", "units": "fires per km2 per year",
        "licence": "NASA open data (attribution)",
        "caveats": "Mostly savanna and crop-residue burning; charcoal production not detected reliably; "
                   "cloud hides wet-season fires. NOAA-20 only in the point layer.",
        "citation": "NASA FIRMS; Schroeder et al. (2014), RSE 143:85-96. doi:10.5067/FIRMS/VIIRS/VNP14IMGT"})
    update_registry("burned_area", {
        "title": "Burned area (MODIS)", "group": "Fire", "type": "burned",
        "urls": {"tiles": {str(y): f"tiles/burned_{y}.pmtiles" for y in range(2001, 2026)},
                 "series": "series/fire.json"},
        "years": list(range(2001, 2026)), "minzoom": 5, "maxzoom": 10,
        "source": "MODIS MCD64A1 v6.1 monthly burned area, annual union per ~500 m cell, "
                  "via Microsoft Planetary Computer",
        "period": "2001-2025", "units": "burned at least once in the year (0/1)",
        "licence": "NASA open data (attribution)",
        "caveats": "~500 m detection misses small/low-intensity burns; cloud limits wet-season detection.",
        "citation": "Giglio et al. (2018), RSE 217:72-85. doi:10.5067/MODIS/MCD64A1.061"})


if __name__ == "__main__":
    main()
