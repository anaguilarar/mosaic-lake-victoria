"""Generic raster -> PMTiles tiler (pure Python: rasterio + mercantile + Pillow + pmtiles).

Two stages:
1. warp_to_mercator(): reproject the source to EPSG:3857 at the max-zoom resolution into a tiled
   GTiff in prep/work/, and build internal overviews down to MINZOOM. Resampling is chosen per
   layer (bilinear/average for continuous data; nearest/mode for categorical - never bilinear).
2. cut_tiles(): walk the XYZ tiles intersecting the data bounds; each 256x256 tile is a decimated
   windowed read (GDAL serves it from the right overview), passed to an encoder that returns
   PNG/JPEG/WebP bytes (or None to skip empty tiles); written to MBTiles then converted to PMTiles.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from prep_common import WORK, log, open_mbtiles, put_tile, mbtiles_to_pmtiles

MERC = "EPSG:3857"
TILE = 256
ORIGIN = 20037508.342789244


def zoom_res(z: int) -> float:
    return 2 * ORIGIN / (TILE * (1 << z))


def warp_to_mercator(src_path: Path, out_name: str, maxzoom: int, resampling: Resampling,
                     dtype=None, nodata=None, src_nodata=None, bands=None,
                     pad_m: float = 0.0, pad_fill: float | None = None,
                     ovr: Resampling | None = None) -> Path:
    """Reproject to EPSG:3857 snapped to the maxzoom tile grid; skipped if the file already exists."""
    out = WORK / f"{out_name}_merc_z{maxzoom}.tif"
    if out.exists() and out.stat().st_mtime >= Path(src_path).stat().st_mtime:
        log.info("exists: %s", out.name)
        return out
    res = zoom_res(maxzoom)
    with rasterio.open(src_path) as src:
        bands = bands or list(range(1, src.count + 1))
        left, bottom, right, top = transform_bounds(src.crs, MERC, *src.bounds, densify_pts=51)
        left -= pad_m; right += pad_m; bottom -= pad_m; top += pad_m
        left, top = math.floor((left + ORIGIN) / res) * res - ORIGIN, ORIGIN - math.floor((ORIGIN - top) / res) * res
        width = math.ceil((right - left) / res)
        height = math.ceil((top - bottom) / res)
        profile = dict(driver="GTiff", crs=MERC, transform=from_origin(left, top, res, res),
                       width=width, height=height, count=len(bands),
                       dtype=dtype or src.dtypes[0], nodata=nodata,
                       tiled=True, blockxsize=512, blockysize=512, compress="DEFLATE",
                       predictor=2, BIGTIFF="IF_SAFER", num_threads="ALL_CPUS")
        tmp = out.with_suffix(".tmp.tif")
        with rasterio.open(tmp, "w", **profile) as dst:
            for i, b in enumerate(bands, start=1):
                log.info("warping %s band %d -> %s (%dx%d)", src_path.name, b, out.name, width, height)
                reproject(rasterio.band(src, b), rasterio.band(dst, i),
                          src_nodata=src_nodata,
                          dst_nodata=pad_fill if pad_fill is not None else nodata,
                          resampling=resampling, num_threads=4, warp_mem_limit=512)
    if ovr is None:
        ovr = Resampling.mode if resampling == Resampling.nearest else Resampling.average
    with rasterio.open(tmp, "r+") as ds:
        factors = [2 ** i for i in range(1, maxzoom - 4)]
        log.info("building overviews %s (%s)", factors, ovr.name)
        ds.build_overviews(factors, ovr)
    tmp.replace(out)
    return out


def max_levels(merc_path: Path, minzoom: int, maxzoom: int, strip: int = 512) -> dict[int, Path]:
    """MAX pyramid: one GTiff per zoom below maxzoom, each output cell the max of the 2x2 cells of
    the level above (nodata ignored; nodata only where all four are nodata). GDAL overviews and
    decimated reads have no MAX resampling, so zoomed-out tiles are read from these files instead.
    Max of maxes is exact, so a cell is coloured if any part of it had the value."""
    levels = {maxzoom: merc_path}
    prev = merc_path
    for z in range(maxzoom - 1, minzoom - 1, -1):
        out = merc_path.with_name(f"{merc_path.stem}_max_z{z}.tif")
        if not out.exists() or out.stat().st_mtime < merc_path.stat().st_mtime:
            with rasterio.open(prev) as src:
                nd = src.nodata
                H, W = math.ceil(src.height / 2), math.ceil(src.width / 2)
                prof = src.profile | dict(width=W, height=H, transform=src.transform * src.transform.scale(2),
                                          tiled=True, blockxsize=512, blockysize=512, compress="DEFLATE")
                tmp = out.with_suffix(".tmp.tif")
                with rasterio.open(tmp, "w", **prof) as dst:
                    for r0 in range(0, H, strip):
                        h = min(strip, H - r0)
                        a = src.read(window=Window(0, 2 * r0, 2 * W, 2 * h), boundless=True, fill_value=nd)
                        a = a.reshape(src.count, h, 2, W, 2)
                        valid = a != nd
                        m = np.where(valid, a, 0).max(axis=(2, 4)).astype(a.dtype)
                        m[~valid.any(axis=(2, 4))] = nd
                        dst.write(m, window=Window(0, r0, W, h))
                tmp.replace(out)
            log.info("max level z%d: %s (%dx%d)", z, out.name, W, H)
        levels[z] = prev = out
    return levels


def cut_tiles(merc_path: Path, pm_out: Path, name: str, fmt: str, minzoom: int, maxzoom: int,
              encoder, resampling: Resampling, extra_meta=None, levels: dict[int, Path] | None = None):
    """Cut XYZ tiles from the mercator raster and write <pm_out>.pmtiles. With `levels` (from
    max_levels), each zoom is read from its own pre-aggregated raster instead of the overviews."""
    mb = WORK / (pm_out.stem + ".mbtiles")
    with rasterio.open(merc_path) as src0:
        w, s, e, n = transform_bounds(MERC, "EPSG:4326", *src0.bounds)
    db = open_mbtiles(mb, name, fmt, minzoom, maxzoom, (w, s, e, n), extra_meta)
    total = written = 0
    for z in range(minzoom, maxzoom + 1):
        with rasterio.open((levels or {}).get(z, merc_path)) as src:
            for t in mercantile.tiles(w, s, e, n, z):
                b = mercantile.xy_bounds(t)
                win = from_bounds(b.left, b.bottom, b.right, b.top, transform=src.transform)
                data = src.read(window=win, out_shape=(src.count, TILE, TILE),
                                resampling=resampling, boundless=True,
                                fill_value=src.nodata if src.nodata is not None else 0)
                png = encoder(data)
                total += 1
                if png is not None:
                    put_tile(db, z, t.x, t.y, png)
                    written += 1
        db.commit()
        log.info("%s z%d: %d/%d tiles", pm_out.stem, z, written, total)
    db.close()
    mbtiles_to_pmtiles(mb, pm_out, maxzoom)
    mb.unlink()


# ----------------------------------------------------------------- encoders

def encode_png(rgba: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgba).save(buf, "PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def terrain_encoder(data: np.ndarray) -> bytes | None:
    """Mapbox terrain-rgb: h = -10000 + (R*65536 + G*256 + B) * 0.1."""
    h = data[0].astype("f8")
    v = np.round((np.where(np.isfinite(h), h, 0) + 10000) / 0.1).astype("u4")
    rgba = np.empty((TILE, TILE, 3), "u1")
    rgba[..., 0] = (v >> 16) & 255
    rgba[..., 1] = (v >> 8) & 255
    rgba[..., 2] = v & 255
    return encode_png(rgba)


def make_s2_encoder(stretch_max: float, gamma: float, quality: int = 82):
    """WebP with alpha: JPEG edge tiles paint their no-data margins opaque black, so imagery
    tiles must carry transparency where all bands are zero."""
    lut = (255 * (np.linspace(0, 1, 4096) ** (1 / gamma))).astype("u1")

    def enc(data: np.ndarray) -> bytes | None:
        if not data.any():
            return None
        idx = np.clip(data.astype("f4") / stretch_max, 0, 1) * 4095
        rgb = lut[idx.astype("u2")]
        rgba = np.empty((data.shape[1], data.shape[2], 4), "u1")
        rgba[..., :3] = np.moveaxis(rgb, 0, -1)
        rgba[..., 3] = np.where(data.any(0), 255, 0)
        buf = io.BytesIO()
        Image.fromarray(rgba).save(buf, "WEBP", quality=quality)
        return buf.getvalue()
    return enc


def make_colormap_encoder(colormap: dict[int, tuple], nodata: int):
    """Categorical/stepped RGBA encoder: value -> (r,g,b,a); unmapped & nodata transparent."""
    lut = np.zeros((256, 4), "u1")
    for v, rgba in colormap.items():
        lut[v] = rgba
    lut[nodata] = (0, 0, 0, 0)

    def enc(data: np.ndarray) -> bytes | None:
        rgba = lut[data[0]]
        if not rgba[..., 3].any():
            return None
        return encode_png(rgba)
    return enc
