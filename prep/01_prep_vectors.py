"""P0.1 - basin boundary, outside-basin mask and lake polygon as small GeoJSON files.

Outputs (EPSG:4326): data/vectors/basin.geojson, basin_mask.geojson (world ring with basin hole,
for dimming outside the basin), lake.geojson (WBM class 2, main lake only, for the water-level
click target). Registers the 'basin' entry in the layer registry.

Usage:  python 01_prep_vectors.py
"""
import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from shapely.geometry import Polygon, shape

from prep_common import BASIN_GPKG, BASIN_LAYER, VECTORS, WBM, log, setup_logging, update_registry


def main():
    setup_logging()
    basin = gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER)[["geometry"]].to_crs("EPSG:4326")
    simp = basin.simplify(0.0008)                                    # ~90 m
    simp.to_frame("geometry").to_file(VECTORS / "basin.geojson", driver="GeoJSON")
    log.info("basin.geojson: %.0f KB", (VECTORS / "basin.geojson").stat().st_size / 1e3)

    world = Polygon([(26.7, -6.5), (38.4, -6.5), (38.4, 3.7), (26.7, 3.7)])  # data bbox + terrain padding
    mask = gpd.GeoDataFrame(geometry=[world.difference(simp.union_all())], crs="EPSG:4326")
    mask.to_file(VECTORS / "basin_mask.geojson", driver="GeoJSON")

    with rasterio.open(WBM) as src:                                   # lake polygon at ~150 m
        f = 5
        a = src.read(1, out_shape=(src.height // f, src.width // f), resampling=rasterio.enums.Resampling.mode)
        t = src.transform * src.transform.scale(src.width / a.shape[1], src.height / a.shape[0])
    polys = [shape(g) for g, v in features.shapes((a == 2).astype("u1"), transform=t) if v == 1]
    lake = max(polys, key=lambda p: p.area)                           # main lake only
    gpd.GeoDataFrame(geometry=[lake.simplify(0.002)], crs="EPSG:4326").to_file(
        VECTORS / "lake.geojson", driver="GeoJSON")
    log.info("lake.geojson: %.0f km2 approx", lake.area * 111.32 * 110.57)

    update_registry("basin", {
        "title": "Lake Victoria Basin boundary", "group": "Base", "type": "vector",
        "urls": {"boundary": "vectors/basin.geojson", "mask": "vectors/basin_mask.geojson",
                 "lake": "vectors/lake.geojson"},
        "source": "ICPAC geoportal (geonode:lv_basin), 2019; lake from Copernicus GLO-30 WBM",
        "licence": "ICPAC: not specified (confirm before public release); WBM: Copernicus, free with attribution",
        "citation": "ICPAC Geoportal; Copernicus DEM GLO-30 (ESA/Airbus)"})


if __name__ == "__main__":
    main()
