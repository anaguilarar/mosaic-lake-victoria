"""SPI-3 (3-month Standardized Precipitation Index) from the existing CHIRPS monthly stack.

Method: 3-month rolling totals; per cell and calendar month, a gamma distribution is fitted to the
1991-2020 calibration totals with the Thom (1958) approximation (the standard SPI implementation),
with the zero-rain probability handled as a mixed distribution (q + (1-q)*GammaCDF); SPI is the
standard normal quantile of that probability, clamped to [-3, 3].

Writes:
    climate/app/spi3.tif          int16 x0.01, one band per month (label = window END month)
    climate/app/spi3_cells.bin    [row][col][month] int16 x0.01 - one range request per cell
    series/spi3_basin.json        basin land-only monthly mean SPI
    updates app_meta.json (months_spi3) and the registry.

Usage:  python prep/09_prep_spi.py
"""
import json

import numpy as np
import rasterio
from scipy.stats import gamma as sgamma
from scipy.stats import norm

from prep_common import CLIMATE, NORMAL, SERIES, log, setup_logging, update_registry

APP = CLIMATE / "app"
NODATA = -32768
WINDOW = 3


def main():
    setup_logging()
    with rasterio.open(CLIMATE / "precip_monthly.tif") as r:
        a = r.read().astype("f8")
        labels = list(r.descriptions)
        t = r.transform
    a[a == NODATA] = np.nan
    a /= 10.0

    # 3-month rolling totals; label = end month
    k = np.ones(WINDOW)
    tot = np.full_like(a, np.nan)
    for i in range(WINDOW - 1, a.shape[0]):
        tot[i] = a[i - WINDOW + 1 : i + 1].sum(0)
    months = np.array([int(lb[5:7]) for lb in labels])
    years = np.array([int(lb[:4]) for lb in labels])
    calib = (years >= NORMAL[0]) & (years <= NORMAL[1])

    spi = np.full_like(tot, np.nan, dtype="f8")
    qc_normal = np.full((12,) + tot.shape[1:], np.nan)      # mean calibration 3-month total (mm)
    qc_q0 = np.full((12,) + tot.shape[1:], np.nan)          # zero-rain probability in calibration
    eps = 1e-9
    for m in range(1, 13):
        sel = (months == m)
        cal = sel & calib
        x = tot[cal]                                       # (30, H, W)
        pos = np.where(x > eps, x, np.nan)
        n_all = np.isfinite(x).sum(0).astype("f8")
        n_pos = np.isfinite(pos).sum(0).astype("f8")
        with np.errstate(all="ignore"):
            q0 = (n_all - n_pos) / np.maximum(n_all, 1)    # zero-rain probability
            mean = np.nanmean(pos, axis=0)
            lnmean = np.log(np.maximum(mean, eps))
            meanln = np.nanmean(np.log(np.maximum(pos, eps)), axis=0)
            A = np.maximum(lnmean - meanln, 1e-6)          # Thom approximation
            shape = (1 + np.sqrt(1 + 4 * A / 3)) / (4 * A)
            scale = mean / shape
            xt = tot[sel]
            cdf = sgamma.cdf(np.maximum(xt, eps), shape[None], scale=scale[None])
            p = q0[None] + (1 - q0[None]) * cdf
            p = np.where(xt <= eps, q0[None] / 2 + 1e-4, p)  # zero months land inside the zero mass
            p = np.clip(p, 1e-4, 1 - 1e-4)
            spi[sel] = norm.ppf(p)
            qc_normal[m - 1] = np.nanmean(x, axis=0)
            qc_q0[m - 1] = q0
        log.info("month %02d fitted (valid cells: %d)", m, int(np.isfinite(shape).sum()))
    spi = np.clip(spi, -3, 3)
    spi[~np.isfinite(tot)] = np.nan
    spi = spi[WINDOW - 1:]
    out_labels = labels[WINDOW - 1:]

    enc = np.where(np.isfinite(spi), np.round(spi * 100), NODATA).astype("i2")
    prof = dict(driver="GTiff", height=enc.shape[1], width=enc.shape[2], count=enc.shape[0],
                dtype="int16", crs="EPSG:4326", transform=t, nodata=NODATA, tiled=True,
                blockxsize=256, blockysize=256, compress="DEFLATE", predictor=2)
    with rasterio.open(APP / "spi3.tif", "w", **prof) as dst:
        dst.write(enc)
        for i, lb in enumerate(out_labels, 1):
            dst.set_band_description(i, lb)
        dst.update_tags(units="SPI (unitless)", scale_factor="0.01",
                        calibration=f"{NORMAL[0]}-{NORMAL[1]}", window="3 months, label = end month")
    log.info("spi3.tif: %d bands, %.1f MB", len(out_labels), (APP / 'spi3.tif').stat().st_size / 1e6)

    flat = np.ascontiguousarray(np.moveaxis(enc, 0, -1).astype("<i2"))
    (APP / "spi3_cells.bin").write_bytes(flat.tobytes())

    meta = json.loads((APP / "app_meta.json").read_text(encoding="utf-8"))
    meta["months_spi3"] = {"start": out_labels[0], "end": out_labels[-1], "n": len(out_labels)}
    (APP / "app_meta.json").write_text(json.dumps(meta), encoding="utf-8")

    with rasterio.open(APP / "landmask.tif") as lm:
        land = lm.read(1) == 10
    series = {lb: round(float(np.nanmean(np.where(land, s, np.nan))), 2) for lb, s in zip(out_labels, spi)}
    (SERIES / "spi3_basin.json").write_text(json.dumps(
        {"units": "SPI-3", "calibration": f"{NORMAL[0]}-{NORMAL[1]}",
         "mask": "basin land only", "monthly": series}), encoding="utf-8")

    # QC products: per-calendar-month window normal + zero-rain probability, for reliability flags
    qc = np.concatenate([qc_normal, qc_q0 * 100])
    qlabels = [f"normal_mm_{m:02d}" for m in range(1, 13)] + [f"q0_pct_{m:02d}" for m in range(1, 13)]
    qenc = np.where(np.isfinite(qc), np.round(qc * 10), NODATA).astype("i2")
    with rasterio.open(APP / "spi3_qc.tif", "w", **{**prof, "count": 24}) as dst:
        dst.write(qenc)
        for i, lb in enumerate(qlabels, 1):
            dst.set_band_description(i, lb)
        dst.update_tags(scale_factor="0.1",
                        caution="SPI is unreliable where the calibration window normal is small or "
                                "zero-inflated (low-normal flag: normal < 30 mm or q0 > 20%)")
    log.info("spi3_qc.tif written")

    # requested QC list: cells < -2.5 in the latest month, with their window normals and q0
    import csv
    last = len(out_labels) - 1
    lm = int(out_labels[last][5:7]) - 1
    sel = np.where(spi[last] < -2.5)
    with open(APP.parent.parent.parent / "prep" / "work" / f"spi_qc_{out_labels[last]}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lat", "lon", "spi", "normal_window_mm", "q0_pct", "low_normal_flag"])
        for r0, c0 in zip(*sel):
            lat = t.f + t.e * (r0 + 0.5)
            lon = t.c + t.a * (c0 + 0.5)
            nm = qc_normal[lm, r0, c0]
            q = qc_q0[lm, r0, c0] * 100
            w.writerow([round(lat, 3), round(lon, 3), round(float(spi[last, r0, c0]), 2),
                        round(float(nm), 1), round(float(q), 1), int(nm < 30 or q > 20)])
    log.info("QC list for %s: %d cells < -2.5", out_labels[last], len(sel[0]))

    update_registry("spi3", {
        "title": "Drought index (SPI-3)", "group": "Climate", "type": "climate-monthly",
        "urls": {"stack": "climate/app/spi3.tif", "cells": "climate/app/spi3_cells.bin",
                 "qc": "climate/app/spi3_qc.tif",
                 "series": "series/spi3_basin.json"},
        "palette": {"value": "BrBG diverging, centred 0, fixed -3..3 (values clipped to ±3)"},
        "source": "SPI-3 computed from CHIRPS v3.0 monthly totals (gamma fit, Thom 1958; "
                  f"zero-rain mixed distribution), calibration {NORMAL[0]}-{NORMAL[1]}",
        "period": f"{out_labels[0]} to {out_labels[-1]}", "units": "SPI (unitless)",
        "licence": "Derived from CHIRPS v3.0 (CC-BY-4.0)",
        "citation": "McKee, Doesken & Kleist (1993), 8th Conf. Applied Climatology; "
                    "Funk et al. (2015), Scientific Data 2:150066"})


if __name__ == "__main__":
    main()
