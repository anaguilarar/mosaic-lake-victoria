"""Rivers (HydroRIVERS, Strahler >= 4) and sub-basins as vector context layers.

Downloads HydroRIVERS v1.0 Africa (if missing), clips to the basin, keeps ORD_STRA >= 4, simplifies
by stream order, and writes data/vectors/rivers.geojson. Sub-basins are reused verbatim from
analysis/flood_frequency/inputs/subbasins.gpkg (layer `subbasins`) once that file exists and is
approved; until then the layer is registered as pending.

Usage:  python prep/10_prep_rivers.py
"""
import zipfile

import geopandas as gpd
import pyogrio
import requests

from prep_common import BASIN_GPKG, BASIN_LAYER, MOSAIC, VECTORS, WORK, log, setup_logging, update_registry

HYDRORIVERS_URL = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_af_shp.zip"
SUBBASINS = MOSAIC / "analysis" / "flood_frequency" / "inputs" / "subbasins.gpkg"
MIN_ORDER = 4


def fetch_hydrorivers():
    d = WORK / "hydrosheds"
    shp = list(d.rglob("HydroRIVERS_v10_af.shp"))
    if shp:
        return shp[0]
    d.mkdir(parents=True, exist_ok=True)
    z = d / "HydroRIVERS_v10_af_shp.zip"
    if not z.exists():
        log.info("downloading %s", HYDRORIVERS_URL)
        with requests.get(HYDRORIVERS_URL, stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(z.with_suffix(".part"), "wb") as f:
                for chunk in r.iter_content(1 << 22):
                    f.write(chunk)
        z.with_suffix(".part").replace(z)
        log.info("downloaded %.0f MB", z.stat().st_size / 1e6)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(d)
    return list(d.rglob("HydroRIVERS_v10_af.shp"))[0]


def main():
    setup_logging()
    basin = gpd.read_file(BASIN_GPKG, layer=BASIN_LAYER).to_crs("EPSG:4326")
    geom = basin.union_all()

    shp = fetch_hydrorivers()
    riv = pyogrio.read_dataframe(shp, bbox=tuple(basin.total_bounds),
                                 columns=["HYRIV_ID", "ORD_STRA", "DIS_AV_CMS"])
    riv = riv[riv.ORD_STRA >= MIN_ORDER]
    riv = riv[riv.intersects(geom)]
    # drop in-lake routing: clip ONLY with the detailed native-resolution shoreline. The simplified
    # lake over-covers bays and the Yala swamp and would cut river mouths kilometres short.
    detail = VECTORS / "lake_detailed.geojson"
    lake = gpd.read_file(detail if detail.exists() else VECTORS / "lake.geojson").union_all()
    riv["geometry"] = riv.geometry.difference(lake)
    riv = riv[~riv.geometry.is_empty]
    riv["geometry"] = riv.geometry.simplify(0.0008)
    riv = riv.rename(columns={"ORD_STRA": "order", "DIS_AV_CMS": "dis_cms"})[["order", "dis_cms", "geometry"]]
    riv.to_file(VECTORS / "rivers.geojson", driver="GeoJSON")
    log.info("rivers.geojson: %d reaches (Strahler >= %d), %.0f KB",
             len(riv), MIN_ORDER, (VECTORS / "rivers.geojson").stat().st_size / 1e3)

    sub_entry = {"status": "pending approval of analysis/flood_frequency/inputs/subbasins.gpkg"}
    if SUBBASINS.exists():
        sub = gpd.read_file(SUBBASINS, layer="subbasins").to_crs("EPSG:4326")
        sub[["name", "hybas_level", "area_km2", "geometry"]].to_file(
            VECTORS / "subbasins.geojson", driver="GeoJSON")
        sub_entry = {"url": "vectors/subbasins.geojson", "names": list(sub.name)}
        log.info("subbasins.geojson: %s", list(sub.name))
    else:
        log.warning("sub-basins not found at %s - layer registered as pending", SUBBASINS)

    update_registry("rivers", {
        "title": "Rivers (HydroRIVERS)", "group": "Base", "type": "vector",
        "urls": {"rivers": "vectors/rivers.geojson"}, "subbasins": sub_entry,
        "source": f"HydroRIVERS v1.0 (HydroSHEDS), Strahler order >= {MIN_ORDER}, clipped to the basin",
        "period": "static (derived from ~2000 SRTM)", "units": "stream order; mean discharge m3/s",
        "licence": "HydroSHEDS v1 licence: free for non-commercial and commercial use with attribution",
        "citation": "Lehner, B. & Grill, G. (2013). Hydrological Processes 27:2171-2186. www.hydrosheds.org"})


if __name__ == "__main__":
    main()
