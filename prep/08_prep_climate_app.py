"""P2 prep - app-ready climate files, derived from the step-04 stacks (no re-download).

Reads climate/precip_monthly.tif, tmax_monthly.tif, tmin_monthly.tif (int16 x0.1, 0.05 deg) and the
30 m GLO-30 WBM, and writes to data/climate/app/ and data/series/:

    {var}_{annual|mam|ond}.tif      yearly stacks, complete years only (one band per year)
                                    var: precip (totals, mm), tmean/tmax/tmin (means, degC)
    normals.tif                     1991-2020 normals: 12 bands (precip & tmean x annual/mam/ond
                                    + precip/tmean monthly handled via cell series)
    landmask.tif                    uint8: 1 land, 2 lake/river (WBM 30 m majority per 0.05 cell)
    precip_cells.bin, tmean_cells.bin   per-cell monthly series as flat int16 (x0.1), layout
                                    [row][col][month] so one HTTP range request returns one cell
    app_meta.json                   dims, bbox, months, years, display ranges (p2/p98), scales
    series/precip_basin.json, temp_basin.json   basin means over LAND cells only (lake masked)

Usage:  python prep/08_prep_climate_app.py
"""
import json

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

from prep_common import CLIMATE, NORMAL, SEASONS, SERIES, WBM, log, setup_logging, update_registry

APP = CLIMATE / "app"
NODATA = -32768
SEASON_MONTHS = {"annual": tuple(range(1, 13)), "mam": SEASONS["MAM"], "ond": SEASONS["OND"]}


def read_stack(path):
    with rasterio.open(path) as r:
        a = r.read().astype("f4")
        a[a == NODATA] = np.nan
        return a / 10.0, [d for d in r.descriptions], r.transform, r.crs


def write_tif(path, arr3d, labels, transform, units, scale=10):
    a = np.where(np.isfinite(arr3d), np.round(np.asarray(arr3d) * scale), NODATA).astype("i2")
    prof = dict(driver="GTiff", height=a.shape[1], width=a.shape[2], count=a.shape[0], dtype="int16",
                crs="EPSG:4326", transform=transform, nodata=NODATA, tiled=True, blockxsize=256,
                blockysize=256, compress="DEFLATE", predictor=2)
    with rasterio.open(path, "w", **prof) as dst:
        dst.write(a)
        for i, lb in enumerate(labels, 1):
            dst.set_band_description(i, lb)
        dst.update_tags(units=units, scale_factor=str(1 / scale))
    log.info("wrote %s (%d bands)", path.name, len(labels))


def yearly(monthly, labels, how, season):
    """Complete-season yearly aggregation from a monthly stack."""
    years, out = [], []
    months = SEASON_MONTHS[season]
    per_year = {}
    for i, lb in enumerate(labels):
        y, m = int(lb[:4]), int(lb[5:7])
        if m in months:
            per_year.setdefault(y, []).append(i)
    for y in sorted(per_year):
        if len(per_year[y]) == len(months):
            years.append(y)
            block = monthly[per_year[y]]
            out.append(block.sum(0) if how == "sum" else block.mean(0))
    return np.stack(out), years


def p2p98(a):
    v = a[np.isfinite(a)]
    return [float(np.percentile(v, 2)), float(np.percentile(v, 98))]


def main():
    setup_logging()
    APP.mkdir(parents=True, exist_ok=True)

    precip, plabels, t, _ = read_stack(CLIMATE / "precip_monthly.tif")
    tmax, tlabels, _, _ = read_stack(CLIMATE / "tmax_monthly.tif")
    tmin, _, _, _ = read_stack(CLIMATE / "tmin_monthly.tif")
    n = min(len(plabels), len(tlabels))
    tmean = (tmax[:n] + tmin[:n]) / 2.0
    shape = precip.shape[1:]

    # land / lake mask from the 30 m WBM (majority per 0.05 deg cell)
    frac = np.zeros(shape, "f4")
    with rasterio.open(WBM) as w:
        wat = (w.read(1) > 0).astype("f4")
        reproject(wat, frac, src_transform=w.transform, src_crs=w.crs,
                  dst_transform=t, dst_crs="EPSG:4326", resampling=Resampling.average)
    landmask = np.where(frac >= 0.5, 2, 1).astype("u1")
    write_tif(APP / "landmask.tif", landmask[None].astype("f4") / 10, ["landmask"], t,
              "1 land, 2 mostly water (x10 in file)", scale=100)

    meta = {"width": shape[1], "height": shape[0],
            "transform": [t.a, t.b, t.c, t.d, t.e, t.f],
            "bbox": [t.c, t.f + t.e * shape[0], t.c + t.a * shape[1], t.f],
            "scale": 0.1, "nodata": NODATA, "normal": f"{NORMAL[0]}-{NORMAL[1]}",
            "months": {"start": plabels[0], "n_precip": len(plabels), "n_tmean": n},
            "ranges": {}, "years": {}}

    stacks = {"precip": (precip, plabels, "sum", "mm"),
              "tmean": (tmean, tlabels[:n], "mean", "degC"),
              "tmax": (tmax, tlabels, "mean", "degC"),
              "tmin": (tmin, tlabels, "mean", "degC")}
    normals, normal_labels = [], []
    for var, (mon, labels, how, units) in stacks.items():
        for season in SEASON_MONTHS:
            arr, years = yearly(mon, labels, how, season)
            write_tif(APP / f"{var}_{season}.tif", arr, [str(y) for y in years], t,
                      f"{units}/{'year' if season == 'annual' else season}")
            meta["years"][f"{var}_{season}"] = years
            meta["ranges"][f"{var}_{season}"] = [round(v, 1) for v in p2p98(arr)]
            if var in ("precip", "tmean"):
                sel = [i for i, y in enumerate(years) if NORMAL[0] <= y <= NORMAL[1]]
                normals.append(arr[sel].mean(0))
                normal_labels.append(f"{var}_{season}")
                if var == "precip":
                    with np.errstate(invalid="ignore", divide="ignore"):
                        anom = 100.0 * arr / normals[-1]
                    meta["ranges"][f"precip_{season}_anom"] = [round(v, 1) for v in p2p98(anom)]
                else:
                    anom = arr - normals[-1]
                    meta["ranges"][f"tmean_{season}_anom"] = [round(v, 2) for v in p2p98(anom)]
    write_tif(APP / "normals.tif", np.stack(normals), normal_labels, t, "per-variable units")

    # per-cell monthly series, [row][col][month] so one range request = one cell
    for name, (mon, nm) in {"precip": (precip, len(plabels)), "tmean": (tmean, n)}.items():
        a = np.where(np.isfinite(mon), np.round(mon * 10), NODATA).astype("<i2")
        flat = np.ascontiguousarray(np.moveaxis(a, 0, -1))          # (row, col, month)
        (APP / f"{name}_cells.bin").write_bytes(flat.tobytes())
        log.info("wrote %s_cells.bin (%.1f MB, %d months/cell)", name, flat.nbytes / 1e6, nm)

    (APP / "app_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    # land-only basin series (lake masked), for charts
    land = landmask == 1
    import geopandas as gpd
    from rasterio.features import geometry_mask
    from prep_common import BASIN_GPKG, BASIN_LAYER
    basin = geometry_mask([gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()],
                          out_shape=shape, transform=t, invert=True, all_touched=True)
    m = basin & land
    pm = np.where(m, 1.0, np.nan)
    pa, py = yearly(precip, plabels, "sum", "annual")
    ta, ty = yearly(tmean, tlabels[:n], "mean", "annual")
    (SERIES / "precip_basin.json").write_text(json.dumps({
        "units": "mm", "normal": meta["normal"], "mask": "basin land only (lake excluded via GLO-30 WBM)",
        "monthly": {lb: round(float(np.nanmean(a * pm)), 1) for lb, a in zip(plabels, precip)},
        "annual": {str(y): round(float(np.nanmean(a * pm)), 1) for y, a in zip(py, pa)}}), encoding="utf-8")
    (SERIES / "temp_basin.json").write_text(json.dumps({
        "units": "degC", "normal": meta["normal"], "mask": "basin land only",
        "tmean_annual": {str(y): round(float(np.nanmean(a * pm)), 2) for y, a in zip(ty, ta)}}), encoding="utf-8")
    log.info("basin series rewritten (land only)")

    update_registry("precip", {
        "title": "Precipitation (CHIRPS v3)", "group": "Climate", "type": "climate",
        "urls": {"app": "climate/app/", "series": "series/precip_basin.json"},
        "palette": {"value": "cividis reversed (dry yellow -> wet dark blue)", "anomaly": "BrBG centred 100%"},
        "source": "CHIRPS v3.0 daily, 0.05 deg, ERA5-disaggregated", "period": f"1981-{meta['years']['precip_annual'][-1]}",
        "units": "mm", "licence": "CC-BY-4.0",
        "caveats": "Satellite rainfall over the lake surface is less reliable; basin means use land cells only.",
        "citation": "Funk et al. (2015), Scientific Data 2:150066; CHIRPS v3.0, UCSB Climate Hazards Center"})
    update_registry("temperature", {
        "title": "Temperature (CHIRTS-ERA5)", "group": "Climate", "type": "climate",
        "urls": {"app": "climate/app/", "series": "series/temp_basin.json"},
        "palette": {"value": "magma", "anomaly": "RdBu centred 0"},
        "source": "CHIRTS-ERA5 daily Tmax/Tmin, 0.05 deg; Tmean = (Tmax+Tmin)/2",
        "period": f"1981-{meta['years']['tmean_annual'][-1]}", "units": "degC", "licence": "CC-BY-4.0",
        "citation": "Funk et al. (2019), J. Climate 32:5639-5658; CHIRTS-ERA5, UCSB CHC"})


if __name__ == "__main__":
    main()
