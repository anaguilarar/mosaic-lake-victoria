"""Detailed lake polygon from the GLO-30 WBM class 2 at native resolution.

The visual lake fill must show islands (Ukerewe, Ssese, Rusinga/Mfangano) as holes, so it is built
from the full-resolution water-body mask: largest class-2 polygon, interior rings kept, simplified
<= 0.0003 deg (~33 m). Written as vectors/lake_detailed.geojson (tippecanoe is unavailable on this
machine, so plain GeoJSON stands in for vector PMTiles; ~5-20 MB, fetched once). The old simplified
lake.geojson remains the click target. Rivers are re-clipped by the detailed polygon.

Usage:  python prep/01b_prep_lake_detail.py
"""
import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import shape

from prep_common import VECTORS, WBM, log, setup_logging, update_registry


def main():
    setup_logging()
    with rasterio.open(WBM) as src:
        mask = (src.read(1) == 2).astype("u1")
        t = src.transform
    polys = [shape(g) for g, v in features.shapes(mask, mask=mask.astype(bool), transform=t) if v == 1]
    lake = max(polys, key=lambda p: p.area)
    n_holes = len(lake.interiors)
    lake_s = lake.simplify(0.0003)
    gdf = gpd.GeoDataFrame(geometry=[lake_s], crs="EPSG:4326")
    out = VECTORS / "lake_detailed.geojson"
    gdf.to_file(out, driver="GeoJSON")
    log.info("lake_detailed.geojson: %.0f KB, %d islands as holes, ~%.0f km2",
             out.stat().st_size / 1e3, n_holes, lake.area * 111.32 * 110.57)

    # river clipping lives in 10_prep_rivers.py (single clip with this detailed shoreline)

    update_registry("basin", {
        "title": "Lake Victoria Basin boundary", "group": "Base", "type": "vector",
        "urls": {"boundary": "vectors/basin.geojson", "mask": "vectors/basin_mask.geojson",
                 "lake": "vectors/lake.geojson", "lake_detailed": "vectors/lake_detailed.geojson"},
        "source": "ICPAC geoportal (geonode:lv_basin), 2019; lake shoreline from the Copernicus GLO-30 "
                  "water-body mask (2011-2015), class 2 at native ~30 m, islands as holes",
        "licence": "ICPAC: not specified (confirm before public release); WBM: Copernicus, free with attribution",
        "caveats": "Lake shoreline from the Copernicus GLO-30 water-body mask (2011-2015); it predates "
                   "the 2020/2024 high stands.",
        "citation": "ICPAC Geoportal; Copernicus DEM GLO-30 (ESA/Airbus)"})


if __name__ == "__main__":
    main()
