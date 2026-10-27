"""P0.4 - CHIRPS v3 precipitation and CHIRTS-ERA5 temperature: basin-clipped aggregates.

Reads the daily Zarr stores on Hugging Face ONCE (offline step - the browser never touches daily
data) and writes small static files:

    climate/precip_monthly.tif     monthly totals, mm      (one band per month, 1981-01..end)
    climate/precip_annual.tif      annual totals, mm       (complete years only)
    climate/precip_seasonal.tif    MAM and OND totals per year, mm
    climate/precip_anomaly.tif     annual anomaly vs 1991-2020 normal, mm
    climate/tmax_monthly.tif, tmin_monthly.tif   monthly means, degC; + annual means + anomalies
    series/precip_basin.json, temp_basin.json    basin-mean monthly/annual series for charts

All rasters: EPSG:4326 at 0.05 deg, basin bbox (~133 x 106 px), int16 scaled (x0.1), nodata -32768,
tiled + DEFLATE, band descriptions = period labels. Registry entries included.

Usage:  python 04_prep_climate.py [--only precip|temp]
"""
import argparse
import json

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import xarray as xr
from affine import Affine
from rasterio.features import geometry_mask

from prep_common import (BASIN_GPKG, BASIN_LAYER, BBOX, CHIRPS, CHIRTS, CLIMATE, NORMAL, SEASONS, SERIES,
                         log, setup_logging, update_registry)

NODATA = -32768


def open_da(url, var):
    """Open one variable of a zarr-v3 store over HTTP as a lazy, scaled DataArray clipped to the bbox.

    xarray's HTTP zarr store cannot list group members, so the arrays are opened with zarr directly."""
    import dask.array as dsa
    import zarr
    g = zarr.open_group(url, mode="r")
    a = g[var]
    attrs = dict(a.attrs)
    time = pd.Timestamp("1980-01-01") + pd.to_timedelta(g["time"][:], unit="D")
    lat, lon = g["lat"][:], g["lon"][:]
    da = xr.DataArray(dsa.from_array(a, chunks=a.shards or a.chunks),
                      dims=("time", "lat", "lon"), coords={"time": time, "lat": lat, "lon": lon})
    fill = attrs.get("_FillValue")
    scale = attrs.get("scale_factor", 1.0)
    da = da.where(da != fill) * scale
    da = da.sel(lon=slice(BBOX[0] - 0.05, BBOX[2] + 0.05))
    da = da.sel(lat=slice(*((BBOX[1] - 0.05, BBOX[3] + 0.05) if lat[0] < lat[-1] else (BBOX[3] + 0.05, BBOX[1] - 0.05))))
    log.info("%s %s: %s", url.rsplit('/', 1)[-1], var, dict(da.sizes))
    return da


def grid(da):
    lat, lon = da.lat.values, da.lon.values
    ry, rx = abs(lat[1] - lat[0]), abs(lon[1] - lon[0])
    north = lat.max() + ry / 2
    t = Affine(rx, 0, lon.min() - rx / 2, 0, -ry, north)
    flip = lat[0] < lat[-1]
    return t, flip


def write_stack(path, arr3d, labels, transform, units, scale=10):
    """int16 x0.1 multiband GTiff with band descriptions."""
    a = np.where(np.isfinite(arr3d), np.round(arr3d * scale), NODATA).astype("i2")
    profile = dict(driver="GTiff", height=a.shape[1], width=a.shape[2], count=a.shape[0], dtype="int16",
                   crs="EPSG:4326", transform=transform, nodata=NODATA, tiled=True,
                   blockxsize=256, blockysize=256, compress="DEFLATE", predictor=2)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(a)
        for i, lb in enumerate(labels, 1):
            dst.set_band_description(i, lb)
        dst.update_tags(units=units, scale_factor=str(1 / scale), nodata=str(NODATA))
    log.info("wrote %s: %d bands, %.1f MB", path.name, len(labels), path.stat().st_size / 1e6)


def basin_mask_for(da, transform, flip):
    basin = gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()
    m = ~geometry_mask([basin], out_shape=(da.sizes["lat"], da.sizes["lon"]), transform=transform,
                       invert=False, all_touched=True)
    return np.flipud(m) if flip else m          # mask in array (lat) order


def monthly(da, how):
    m = da.resample(time="1MS")
    return (m.sum(skipna=False) if how == "sum" else m.mean(skipna=False))


def process_precip():
    da = open_da(CHIRPS, "precip")
    t, flip = grid(da)
    mon = monthly(da, "sum").compute()
    arr = mon.values if not flip else mon.values[:, ::-1, :]
    months_idx = pd.to_datetime(mon.time.values)
    labels = [f"{d:%Y-%m}" for d in months_idx]
    write_stack(CLIMATE / "precip_monthly.tif", arr, labels, t, "mm/month")

    years = sorted({d.year for d in months_idx})
    full_years = [y for y in years if sum(d.year == y for d in months_idx) == 12]
    ann = np.stack([arr[[i for i, d in enumerate(months_idx) if d.year == y]].sum(0) for y in full_years])
    write_stack(CLIMATE / "precip_annual.tif", ann, [str(y) for y in full_years], t, "mm/year")

    seas_arr, seas_lab = [], []
    for sname, smonths in SEASONS.items():
        for y in years:
            idx = [i for i, d in enumerate(months_idx) if d.year == y and d.month in smonths]
            if len(idx) == len(smonths):
                seas_arr.append(arr[idx].sum(0))
                seas_lab.append(f"{sname}-{y}")
    write_stack(CLIMATE / "precip_seasonal.tif", np.stack(seas_arr), seas_lab, t, "mm/season")

    normal_years = [y for y in full_years if NORMAL[0] <= y <= NORMAL[1]]
    normal = ann[[full_years.index(y) for y in normal_years]].mean(0)
    write_stack(CLIMATE / "precip_anomaly.tif", ann - normal, [str(y) for y in full_years], t,
                f"mm/year vs {NORMAL[0]}-{NORMAL[1]} normal")

    mask = basin_mask_for(da, t, False)
    if flip:
        mask = mask  # mask built in raster order; arr is raster order already
    series = {
        "units": "mm", "normal": f"{NORMAL[0]}-{NORMAL[1]}",
        "monthly": {lb: round(float(np.nanmean(np.where(mask, a, np.nan))), 1) for lb, a in zip(labels, arr)},
        "annual": {str(y): round(float(np.nanmean(np.where(mask, a, np.nan))), 1) for y, a in zip(full_years, ann)},
    }
    (SERIES / "precip_basin.json").write_text(json.dumps(series), encoding="utf-8")
    update_registry("precip", {
        "title": "Precipitation (CHIRPS v3)", "group": "Climate", "type": "cog-stack",
        "urls": {"monthly": "climate/precip_monthly.tif", "annual": "climate/precip_annual.tif",
                 "seasonal": "climate/precip_seasonal.tif", "anomaly": "climate/precip_anomaly.tif",
                 "series": "series/precip_basin.json"},
        "palette": {"type": "sequential-cbsafe", "name": "viridis"},
        "anomaly_palette": {"type": "diverging-centered-0", "name": "BrBG"},
        "source": "CHIRPS v3.0 daily, 0.05 deg", "period": f"{labels[0]} to {labels[-1]}",
        "units": "mm", "licence": "CC-BY-4.0",
        "citation": "Funk et al. (2015), Scientific Data 2:150066; CHIRPS v3.0, UCSB Climate Hazards Center"})


def process_temp():
    tstack = {}
    labels = None
    t = None
    for var, fname in [("Tmax", "tmax"), ("Tmin", "tmin")]:
        da = open_da(CHIRTS, var)
        t, flip = grid(da)
        mon = monthly(da, "mean").compute()
        arr = mon.values if not flip else mon.values[:, ::-1, :]
        months_idx = pd.to_datetime(mon.time.values)
        labels = [f"{d:%Y-%m}" for d in months_idx]
        write_stack(CLIMATE / f"{fname}_monthly.tif", arr, labels, t, "degC")
        tstack[fname] = (arr, months_idx)

    arr, months_idx = tstack["tmax"]
    tmean = (tstack["tmax"][0] + tstack["tmin"][0]) / 2
    years = sorted({d.year for d in months_idx})
    full = [y for y in years if sum(d.year == y for d in months_idx) == 12]
    ann = np.stack([tmean[[i for i, d in enumerate(months_idx) if d.year == y]].mean(0) for y in full])
    write_stack(CLIMATE / "tmean_annual.tif", ann, [str(y) for y in full], t, "degC")
    normal = ann[[full.index(y) for y in full if NORMAL[0] <= y <= NORMAL[1]]].mean(0)
    write_stack(CLIMATE / "tmean_anomaly.tif", ann - normal, [str(y) for y in full], t,
                f"degC vs {NORMAL[0]}-{NORMAL[1]}")

    da = open_da(CHIRTS, "Tmax")
    mask = basin_mask_for(da, t, False)
    series = {"units": "degC",
              "tmean_annual": {str(y): round(float(np.nanmean(np.where(mask, a, np.nan))), 2)
                               for y, a in zip(full, ann)}}
    (SERIES / "temp_basin.json").write_text(json.dumps(series), encoding="utf-8")
    update_registry("temperature", {
        "title": "Temperature (CHIRTS-ERA5)", "group": "Climate", "type": "cog-stack",
        "urls": {"tmax_monthly": "climate/tmax_monthly.tif", "tmin_monthly": "climate/tmin_monthly.tif",
                 "annual": "climate/tmean_annual.tif", "anomaly": "climate/tmean_anomaly.tif",
                 "series": "series/temp_basin.json"},
        "palette": {"type": "sequential-cbsafe", "name": "magma"},
        "anomaly_palette": {"type": "diverging-centered-0", "name": "RdBu_r"},
        "source": "CHIRTS-ERA5 daily Tmax/Tmin, 0.05 deg", "period": f"{labels[0]} to {labels[-1]}",
        "units": "degC", "licence": "CC-BY-4.0",
        "citation": "Funk et al. (2019), J. Climate 32:5639-5658; CHIRTS-ERA5, UCSB CHC"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["precip", "temp"])
    args = ap.parse_args()
    setup_logging()
    if args.only in (None, "precip"):
        process_precip()
    if args.only in (None, "temp"):
        process_temp()


if __name__ == "__main__":
    main()
