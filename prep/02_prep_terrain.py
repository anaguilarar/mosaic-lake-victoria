"""P0.2 - DEM -> Mapbox terrain-rgb PMTiles for MapLibre setTerrain + hillshade.

Max zoom 11 (measured: z12 would add only 0.7-1.6 m RMSE on 850-2700 m relief - not visible).
Encoding: mapbox terrain-rgb (interval 0.1 m), PNG. Reprojection bilinear, overviews average.

Usage:  python 02_prep_terrain.py
"""
import numpy as np
import rasterio
import scipy.ndimage as nd
from rasterio.enums import Resampling


def fill_padding(path, step=16, sigma=4.0):
    """Replace NaN padding with nearest-edge elevations, smoothed, at 1/step resolution."""
    with rasterio.open(path, "r+") as ds:
        a = ds.read(1)
        bad = ~np.isfinite(a)
        if not bad.any():
            return
        small = a[::step, ::step].copy()
        sbad = ~np.isfinite(small)
        idx = nd.distance_transform_edt(sbad, return_distances=False, return_indices=True)
        filled = small[tuple(idx)]
        smooth = nd.gaussian_filter(filled, sigma)
        filled[sbad] = smooth[sbad]
        up = nd.zoom(filled, step, order=1)[: a.shape[0], : a.shape[1]]
        if up.shape != a.shape:                       # zoom can undershoot by a pixel
            pad = [(0, a.shape[0] - up.shape[0]), (0, a.shape[1] - up.shape[1])]
            up = np.pad(up, pad, mode="edge")
        a[bad] = up[bad]
        ds.write(a, 1)

from prep_common import DEM, MINZOOM, TERRAIN_MAXZOOM, TILES, setup_logging, update_registry
from tiler import cut_tiles, terrain_encoder, warp_to_mercator


def main():
    setup_logging()
    # pad 250 km beyond the DEM: MapLibre terrain renders missing raster-dem tiles as black, so every
    # tile a bounded camera can see must exist. The padding (600 km: no missing-tile black at any reachable camera) is filled with smoothly extrapolated
    # elevations (nearest real edge value, blurred at 16x coarse scale) - a constant fill creates a
    # cliff whose hillshade reads as a ghost outline.
    merc = warp_to_mercator(DEM, "dem_padded", TERRAIN_MAXZOOM, Resampling.bilinear, dtype="float32",
                            pad_m=600_000, pad_fill=float("nan"))
    fill_padding(merc)
    out = TILES / "terrain.pmtiles"
    cut_tiles(merc, out, "GLO-30 terrain-rgb", "png", MINZOOM, TERRAIN_MAXZOOM,
              terrain_encoder, Resampling.bilinear, {"encoding": "mapbox"})
    update_registry("terrain", {
        "title": "Terrain (Copernicus GLO-30)", "group": "Base", "type": "raster-dem",
        "urls": {"pmtiles": "tiles/terrain.pmtiles"}, "encoding": "mapbox",
        "minzoom": MINZOOM, "maxzoom": TERRAIN_MAXZOOM,
        "exaggeration": {"default": 1.8, "min": 1.0, "max": 4.0},
        "source": "Copernicus DEM GLO-30 (~30 m), basin extent", "period": "GLO-30 2021 release",
        "units": "m above sea level",
        "licence": "Copernicus DEM: free use with attribution",
        "caveats": "Terrain beyond the basin extent is synthetic padding for display; elevations are "
                   "neither shown nor queryable there.",
        "citation": "ESA (2021). Copernicus DEM GLO-30. Contains modified Copernicus data."})


if __name__ == "__main__":
    main()
