"""P0.3 - Sentinel-2 annual RGB mosaic -> JPEG PMTiles (base texture draped on the terrain).

Fixed stretch for all bands: reflectance 0-3000 + gamma 2.2 (no per-band percentiles).
Offset check done 2026-10-21: lake-water reflectance 300-460 (min 304) => the post-2022 L2A
+1000 offset was removed (harmonized collection) - no correction needed here.
Mosaic year: TBD - set --year when known; it is written into the registry/attribution.

Usage:  python 03_prep_s2.py [--year 2024]
"""
import argparse

from rasterio.enums import Resampling

from prep_common import MINZOOM, S2, S2_GAMMA, S2_MAXZOOM, S2_STRETCH_MAX, TILES, setup_logging, update_registry
from tiler import cut_tiles, make_s2_encoder, warp_to_mercator


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", default="TBD", help="mosaic year/period for the attribution line")
    args = ap.parse_args()
    setup_logging()
    merc = warp_to_mercator(S2, "s2", S2_MAXZOOM, Resampling.bilinear, dtype="uint16")
    out = TILES / "s2_rgb.pmtiles"
    cut_tiles(merc, out, "Sentinel-2 RGB mosaic", "webp", MINZOOM, S2_MAXZOOM,
              make_s2_encoder(S2_STRETCH_MAX, S2_GAMMA), Resampling.bilinear)
    update_registry("s2_rgb", {
        "title": "Satellite imagery (Sentinel-2)", "group": "Base", "type": "raster",
        "urls": {"pmtiles": "tiles/s2_rgb.pmtiles"},
        "minzoom": MINZOOM, "maxzoom": S2_MAXZOOM,
        "source": "Sentinel-2 L2A annual median mosaic, 30 m",
        "period": str(args.year), "units": "true colour (fixed stretch 0-3000, gamma 2.2)",
        "licence": "Copernicus Sentinel data: free use with attribution",
        "citation": f"Contains modified Copernicus Sentinel-2 data [{args.year}]"})


if __name__ == "__main__":
    main()
