"""Population exposure to recurrent flooding: centre-assignment counting, per sub-basin and basin.

Approved rule: exposure(N) = sum over 100 m population cells of
    population x fraction of the cell flooded >= N years,
where the fraction is the mean of (years_flooded >= N) over the 20 m GFM cells inside each 100 m cell
(a 20 m cell is inside the 100 m cell that contains its centre).

REFUSES to run on placeholder flood data; needs the real flood COG and the approved sub-basins:
    analysis/flood_frequency/outputs/lvb_flood_frequency_2016_2025.tif   (band 1 = years_flooded)
    analysis/flood_frequency/inputs/subbasins.gpkg                       (layer subbasins)
    data/query/pop_100m.tif                                              (11_prep_worldpop.py)

Writes data/series/flood_exposure.json and outputs/flood_exposure.csv (rows: region x N 1..10),
labelled exposure (people in place), not risk.

Usage:  python prep/13_exposure.py
"""
import csv
import json

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from pyproj import Transformer

from prep_common import BASIN_GPKG, BASIN_LAYER, DATA, FLOOD_COG, MOSAIC, SERIES, log, setup_logging

SUBBASINS = MOSAIC / "analysis" / "flood_frequency" / "inputs" / "subbasins.gpkg"
POP = DATA / "query" / "pop_100m.tif"
NS = range(1, 11)
STRIP = 1024                                                 # 20 m rows per strip


def main():
    setup_logging()
    for f, msg in [(FLOOD_COG, "real flood COG (server run)"), (SUBBASINS, "approved sub-basins"),
                   (POP, "pop_100m.tif (11_prep_worldpop.py)")]:
        if not f.exists():
            raise SystemExit(f"missing {msg}: {f}")
    with rasterio.open(FLOOD_COG) as fl:
        if "PLACEHOLDER" in (fl.tags().get("PLACEHOLDER", "") + fl.tags().get("note", "")).upper():
            raise SystemExit("flood COG is placeholder data - exposure must not be computed from it")

    with rasterio.open(POP) as p:
        pop = p.read(1)
        pop_t, pop_crs = p.transform, p.crs
        pop = np.where(pop > 0, pop, 0)

    # fraction flooded >= N per 100 m cell = mean of (years >= N) over the 20 m cells whose centre lies in
    # that cell: count 20 m cells per 100 m cell (den) and flooded ones (num), in row strips. Memory ~2 GB.
    # (Whole-layer reprojection needed ~10 GB and ran the laptop out of memory on 2026-10-26; strip-wise
    # reprojection was ~5 h. This counts cell centres directly and takes minutes.)
    H, W = pop.shape
    num = {N: np.zeros(H * W, "i4") for N in NS}
    den = np.zeros(H * W, "i4")
    to_ll = None
    with rasterio.open(FLOOD_COG) as fl:
        to_ll = Transformer.from_crs(fl.crs, pop_crs, always_xy=True)
        xs = fl.transform.c + (np.arange(fl.width) + 0.5) * fl.transform.a
        for r0 in range(0, fl.height, STRIP):
            win = rasterio.windows.Window(0, r0, fl.width, min(STRIP, fl.height - r0))
            years = fl.read(1, window=win).ravel()           # uint8, 255 nodata
            ys = fl.transform.f + (np.arange(r0, r0 + win.height) + 0.5) * fl.transform.e
            gx, gy = np.meshgrid(xs, ys)
            lon, lat = to_ll.transform(gx.ravel(), gy.ravel())
            del gx, gy
            col = np.floor((lon - pop_t.c) / pop_t.a).astype("i8")
            row = np.floor((lat - pop_t.f) / pop_t.e).astype("i8")
            ok = (col >= 0) & (col < W) & (row >= 0) & (row < H)
            idx = row[ok] * W + col[ok]; v = years[ok]
            del lon, lat, col, row, ok
            den += np.bincount(idx, minlength=H * W).astype("i4")
            fl_ = v != 255
            idx, v = idx[fl_ & (v >= 1)], v[fl_ & (v >= 1)]
            for N in NS:
                num[N] += np.bincount(idx[v >= N], minlength=H * W).astype("i4")
            log.info("rows %d-%d of %d", r0, r0 + win.height, fl.height)
    den = den.reshape(H, W).astype("f4"); den[den == 0] = np.inf   # no 20 m cells -> fraction 0
    frac = {}
    for N in NS:
        frac[N] = num.pop(N).reshape(H, W).astype("f4") / den
        log.info("N=%d: mean flooded fraction %.4f", N, float(frac[N].mean()))
    del den

    regions = {"Lake Victoria Basin": gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).union_all()}
    for r in gpd.read_file(SUBBASINS, layer="subbasins").itertuples():
        regions[r.name] = r.geometry

    out = {"method": "WorldPop 2020 population x share of each 100 m cell flooded in >= N years "
                     "(20 m GFM years_flooded cells, 2016-2025, each assigned to the 100 m cell containing its centre)",
           "label": "exposure (people in place), not risk", "regions": {}}
    rows = [["region", "N_years", "exposed_population"]]
    for name, geom in regions.items():
        m = ~geometry_mask([geom], out_shape=pop.shape, transform=pop_t, invert=False)
        vals = {}
        for N in NS:
            e = float((pop * frac[N] * m).sum())
            vals[str(N)] = round(e)
            rows.append([name, N, round(e)])
        out["regions"][name] = vals
        log.info("%s: exposed >=1y %.0f, >=3y %.0f, >=5y %.0f", name, vals["1"], vals["3"], vals["5"])

    (SERIES / "flood_exposure.json").write_text(json.dumps(out), encoding="utf-8")
    dest = MOSAIC / "analysis" / "flood_frequency" / "outputs" / "flood_exposure.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", newline="") as f:
        csv.writer(f).writerows(rows)
    log.info("wrote %s and series/flood_exposure.json", dest)


if __name__ == "__main__":
    main()
