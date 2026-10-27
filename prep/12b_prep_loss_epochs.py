"""Cumulative tree-cover-loss epochs as pre-coloured tiles.

MapLibre cannot style a raster by its value (no raster-color), so "cumulative loss up to the slider
year" is approximated by five pre-rendered cumulative layers: loss <= 2005, 2010, 2015, 2020, latest.
The slider snaps to these epochs; the click panel still reports exact annual km2.

Needs prep/work/hansen_loss_clip.tif from 12_prep_hansen.py (no re-download).

Usage:  python prep/12b_prep_loss_epochs.py
"""
import json

import numpy as np
import rasterio
from rasterio.enums import Resampling

from prep_common import TILES, WORK, log, setup_logging, update_registry
from tiler import cut_tiles, make_colormap_encoder, warp_to_mercator

RED = (178, 24, 43, 230)


def main():
    setup_logging()
    src = WORK / "hansen_loss_clip.tif"
    if not src.exists():
        raise SystemExit("run 12_prep_hansen.py first (hansen_loss_clip.tif missing)")
    with rasterio.open(src) as s:
        loss = s.read(1)
        prof = s.profile

    max_code = int(loss.max())
    max_year = 2000 + max_code
    epochs = sorted({y for y in (2005, 2010, 2015, 2020) if y < max_year} | {max_year})
    log.info("epochs: %s", epochs)

    urls = {}
    for y in epochs:
        code = y - 2000
        mask = ((loss > 0) & (loss <= code)).astype("u1")
        f = WORK / f"loss_le_{y}.tif"
        with rasterio.open(f, "w", **prof) as d:
            d.write(mask, 1)
        merc = warp_to_mercator(f, f"loss_le_{y}", 12, Resampling.nearest, dtype="uint8")  # 0 is DATA
        out = TILES / f"loss_le_{y}.pmtiles"
        cut_tiles(merc, out, f"tree-cover loss <= {y}", "png", 5, 12,
                  make_colormap_encoder({1: RED}, 0), Resampling.nearest)
        urls[str(y)] = f"tiles/loss_le_{y}.pmtiles"

    # update the forest_loss registry entry in place
    from prep_common import META
    reg = json.loads((META / "layers.json").read_text(encoding="utf-8"))
    for l in reg["layers"]:
        if l["id"] == "forest_loss":
            l["urls"] = {k: v for k, v in l["urls"].items() if k in ("cover", "series")}
            l["urls"]["epochs"] = urls
            l["epochs"] = epochs
            l["caveats"] = (l.get("caveats", "") +
                            " Map shows cumulative loss at 5-year epochs (MapLibre cannot style rasters "
                            "by value); the panel reports exact annual areas.")
    (META / "layers.json").write_text(json.dumps(reg, indent=1), encoding="utf-8")
    log.info("registry updated with %d epoch layers", len(epochs))


if __name__ == "__main__":
    main()
