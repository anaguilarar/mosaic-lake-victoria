"""P1.6 - reference labels: OSM place names (Protomaps basemap extract) + admin boundaries (geoBoundaries).

1. Place names. The vector tiles are an extract of the Protomaps daily OSM basemap (schema v4,
   Planetiler), cut to the basin bbox with go-pmtiles (not run from here; the CLI is a separate download):
       pmtiles extract https://build.protomaps.com/20261022.pmtiles data/tiles/osm_basemap.pmtiles \
               --bbox=29.24,-4.04,35.85,1.26 --maxzoom=12
   -> 67 MB (under GitHub's 100 MB file limit; z13 was 148 MB), OSM replication time 2026-10-22.
   Villages (from z11) are in the z12 tiles; MapLibre overzooms them above z12. Only label layers are drawn (places, water names, natural
   areas); roads and buildings stay in the archive but are not styled. Glyphs (Noto Sans Regular/Medium/
   Italic, ranges 0-511, 4608-5119 Ethiopic, 8192-8447) are hosted in data/fonts/ from
   protomaps/basemaps-assets, so the map needs no third-party font server.

2. Admin boundaries. geoBoundaries gbOpen ADM1 + ADM2 for KEN, UGA, TZA, RWA, BDI (simplified geometry
   from the geoBoundaries API), clipped to the basin polygon and simplified again (~100 m), plus one
   label point per clipped unit (representative point). Each boundary keeps its own source licence:
   they differ by country and level (Public Domain, CC0, CC BY 4.0, CC BY 3.0 IGO, ODbL) and are listed
   in the registry entry. Cite geoBoundaries as Runfola et al. (2020). GADM is not used.

Outputs: data/vectors/admin1.geojson, admin2.geojson, admin_labels.geojson; registry entries
'osm_labels' and 'admin_boundaries'.

Usage:  python 16_prep_labels.py
"""
import json

import geopandas as gpd
import pandas as pd
import requests

from prep_common import DATA, TILES, log, setup_logging, update_registry

COUNTRIES = {"KEN": "Kenya", "UGA": "Uganda", "TZA": "Tanzania", "RWA": "Rwanda", "BDI": "Burundi"}
API = "https://www.geoboundaries.org/api/current/gbOpen/{iso}/{level}/"
SIMPLIFY_DEG = 0.001          # ~110 m: invisible at the app's zooms, keeps the GeoJSON small
VEC = DATA / "vectors"


def fetch(iso, level):
    meta = requests.get(API.format(iso=iso, level=level), timeout=60).json()
    gj = requests.get(meta["simplifiedGeometryGeoJSON"], timeout=300).json()
    g = gpd.GeoDataFrame.from_features(gj["features"], crs="EPSG:4326")
    g = g.rename(columns={"shapeName": "name"})[["name", "geometry"]]
    g["iso"] = iso; g["country"] = COUNTRIES[iso]; g["level"] = level
    info = {"country": COUNTRIES[iso], "level": level, "type": meta.get("boundaryCanonical"),
            "year": meta.get("boundaryYearRepresented"), "source": meta.get("boundarySource"),
            "licence": meta.get("boundaryLicense"), "boundaryID": meta.get("boundaryID")}
    return g, info


def main():
    setup_logging()
    basin = gpd.read_file(VEC / "basin.geojson").to_crs("EPSG:4326")
    basin_geom = basin.union_all() if hasattr(basin, "union_all") else basin.unary_union
    provenance, labels = [], []
    for level in ("ADM1", "ADM2"):
        parts = []
        for iso in COUNTRIES:
            g, info = fetch(iso, level)
            g = g[g.intersects(basin_geom)].copy()
            if g.empty:
                continue
            full_km2 = g.to_crs("EPSG:32736").area / 1e6
            g["geometry"] = g.geometry.intersection(basin_geom).simplify(SIMPLIFY_DEG, preserve_topology=True)
            g = g[~g.geometry.is_empty]
            # drop slivers where a unit only grazes the basin outline (border mismatch between datasets):
            # under 2 km2 inside AND under 10 % of the unit - otherwise they get stray labels
            in_km2 = g.to_crs("EPSG:32736").area / 1e6
            keep = ~((in_km2 < 2) & (in_km2 < 0.1 * full_km2.loc[g.index]))
            if (~keep).any():
                log.info("%s %s: dropped %d boundary slivers", iso, level, int((~keep).sum()))
            g = g[keep]
            info["units_in_basin"] = int(len(g))
            provenance.append(info)
            parts.append(g)
            log.info("%s %s: %d units in the basin (%s; %s)", iso, level, len(g), info["type"], info["licence"])
        gdf = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
        out = VEC / f"{level.lower()}.geojson"
        out.write_text(gdf.to_json(drop_id=True), encoding="utf-8")
        log.info("wrote %s (%d units, %.0f kB)", out, len(gdf), out.stat().st_size / 1e3)
        pts = gdf.copy()
        pts["geometry"] = gdf.geometry.representative_point()
        labels.append(pts)
    lab = gpd.GeoDataFrame(pd.concat(labels, ignore_index=True), crs="EPSG:4326")
    (VEC / "admin_labels.geojson").write_text(lab.to_json(drop_id=True), encoding="utf-8")

    update_registry("osm_labels", {
        "title": "Place names", "group": "Base", "type": "vector",
        "urls": {"tiles": "tiles/osm_basemap.pmtiles", "glyphs": "fonts/{fontstack}/{range}.pbf"},
        "minzoom": 0, "maxzoom": 12,
        "source": "OpenStreetMap via the Protomaps daily basemap (build 2026-10-22, schema v4, Planetiler 0.10.2)",
        "period": "OSM data as of 2026-10-22",
        "units": "labels only: countries, cities, towns, villages (from z11), lakes, rivers, protected areas",
        "licence": "ODbL 1.0 - © OpenStreetMap contributors",
        "citation": "© OpenStreetMap contributors (openstreetmap.org/copyright). Basemap tiles: Protomaps (protomaps.com). "
                    "Fonts: Noto Sans (SIL Open Font License) via protomaps/basemaps-assets.",
        "caveats": "Volunteered geographic information: coverage and spelling vary; label positions are OSM points, "
                   "not authoritative gazetteer locations."})
    update_registry("admin_boundaries", {
        "title": "Admin boundaries", "group": "Base", "type": "vector",
        "urls": {"adm1": "vectors/adm1.geojson", "adm2": "vectors/adm2.geojson", "labels": "vectors/admin_labels.geojson"},
        "source": "geoBoundaries gbOpen ADM1 + ADM2 (simplified), Kenya, Uganda, Tanzania, Rwanda, Burundi; clipped to the basin",
        "period": "boundary years vary by country (2006-2021; see provenance)",
        "units": "ADM1 and ADM2 polygons; names at mid zoom",
        "licence": "per boundary - see provenance (Public Domain, CC0, CC BY 4.0, CC BY 3.0 IGO, ODbL); geoBoundaries itself CC BY 4.0",
        "citation": "Runfola, D. et al. (2020) geoBoundaries: A global database of political administrative boundaries. "
                    "PLoS ONE 15(4): e0231866. doi:10.1371/journal.pone.0231866",
        "caveats": "Boundaries are indicative and not an official delimitation. Uganda ADM1 is the 4 regions (2017, from OSM) "
                   "and ADM2 the 2006 counties; Tanzania ADM1 is OSM-derived. Not GADM.",
        "provenance": provenance})


if __name__ == "__main__":
    main()
