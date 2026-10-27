"""Shared configuration and helpers for the basin_app data-preparation pipeline (P0).

All outputs land under basin_app/data/ and are static files served as-is:
    data/tiles/*.pmtiles      tile pyramids (terrain, S2 RGB, flood)
    data/climate/*.tif        small multiband COG stacks (CHIRPS/CHIRTS aggregates)
    data/series/*.json        time series (lake level, basin means)
    data/vectors/*.geojson    basin boundary, outside mask, lake polygon
    data/meta/layers.json     layer registry consumed by the frontend
"""
from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

APP = Path(__file__).resolve().parents[1]              # basin_app/
MOSAIC = APP.parent                                     # project root
INPUTS = MOSAIC / "inputs"
DATA = APP / "data"
TILES = DATA / "tiles"
CLIMATE = DATA / "climate"
SERIES = DATA / "series"
VECTORS = DATA / "vectors"
META = DATA / "meta"
WORK = APP / "prep" / "work"                            # intermediates (mercator rasters, mbtiles)

DEM = INPUTS / "DEM_basin_extent.tif"
S2 = INPUTS / "s2_annual_rgb_mosaic_30.tif"
WBM = INPUTS / "lake_victoria_wbm_basin_extent.tif"
BASIN_GPKG = INPUTS / "lake_victoria.gpkg"
BASIN_LAYER = "lv_basin"
FLOOD_COG = MOSAIC / "analysis" / "flood_frequency" / "outputs" / "lvb_flood_frequency_2016_2025.tif"
FLOOD_SEASONAL = MOSAIC / "analysis" / "flood_frequency" / "outputs" / "lvb_flood_frequency_seasonal_2016_2025.tif"
FLOOD_MAX = {
    "max_2020": MOSAIC / "analysis/flood_frequency/outputs/lvb_max_flood_extent_20200401_20200731.tif",
    "max_2024": MOSAIC / "analysis/flood_frequency/outputs/lvb_max_flood_extent_20240401_20240531.tif",
}

BBOX = (29.2388150, -4.0399933, 35.8538291, 1.2644686)  # lon/lat of the shared 30 m grid

# Tiling decisions (see prep/README.md for the measurements behind them)
TERRAIN_MAXZOOM = 11      # z12 adds <= 1.6 m RMSE over z11's 1.4-3.6 m on 850-2700 m relief: not visible
S2_MAXZOOM = 12           # native 30 m
FLOOD_MAXZOOM = 12        # 20 m native ~ z13; z12 keeps size sane; nearest/mode only (no bilinear)
MINZOOM = 5
S2_STRETCH_MAX = 3000.0   # fixed reflectance stretch 0-3000 for all bands
S2_GAMMA = 2.2            # out = 255 * (v/3000)^(1/2.2)

# CHIRPS / CHIRTS zarr stores on Hugging Face
HF = "https://huggingface.co/datasets"
CHIRPS = f"{HF}/aaguilar90/chirps-v3-daily-rnl/resolve/main/chirps-v3-daily-rnl.zarr"
CHIRTS = f"{HF}/aaguilar90/chirts-era5-daily/resolve/main/chirts-era5-daily.zarr"
NORMAL = (1991, 2020)     # climatology for anomalies
SEASONS = {"MAM": (3, 4, 5), "OND": (10, 11, 12)}

log = logging.getLogger("prep")


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    for d in (TILES, CLIMATE, SERIES, VECTORS, META, WORK):
        d.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------- layer registry

def update_registry(layer_id: str, entry: dict):
    """Merge one layer entry into data/meta/layers.json (keyed by id, order preserved)."""
    META.mkdir(parents=True, exist_ok=True)
    path = META / "layers.json"
    reg = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"layers": []}
    entry = {"id": layer_id, **entry}
    ids = [l["id"] for l in reg["layers"]]
    if layer_id in ids:
        reg["layers"][ids.index(layer_id)] = entry
    else:
        reg["layers"].append(entry)
    path.write_text(json.dumps(reg, indent=1), encoding="utf-8")
    log.info("registry updated: %s", layer_id)


# ----------------------------------------------------------------- MBTiles / PMTiles

def open_mbtiles(path: Path, name: str, fmt: str, minzoom: int, maxzoom: int, bounds, extra_meta=None):
    """Create a fresh MBTiles file and return its sqlite connection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
    db.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    meta = {"name": name, "format": fmt, "minzoom": str(minzoom), "maxzoom": str(maxzoom),
            "bounds": ",".join(f"{b:.6f}" for b in bounds), "type": "overlay", "version": "1",
            **(extra_meta or {})}
    db.executemany("INSERT INTO metadata VALUES (?,?)", meta.items())
    return db


def put_tile(db, z: int, x: int, y: int, data: bytes):
    """Insert one XYZ tile (converts to the TMS row scheme MBTiles uses)."""
    db.execute("INSERT OR REPLACE INTO tiles VALUES (?,?,?,?)", (z, x, (1 << z) - 1 - y, sqlite3.Binary(data)))


def mbtiles_to_pmtiles(src: Path, dst: Path, maxzoom: int):
    from pmtiles.convert import mbtiles_to_pmtiles as conv
    if dst.exists():
        dst.unlink()
    conv(str(src), str(dst), maxzoom)
    log.info("wrote %s (%.1f MB)", dst, dst.stat().st_size / 1e6)
