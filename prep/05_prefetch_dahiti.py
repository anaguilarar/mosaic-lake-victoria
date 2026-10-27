"""P0.5 - pre-fetch Lake Victoria water levels from DAHITI into a static JSON.

The API key is read ONLY from the environment variable DAHITI_API_KEY (never hard-coded, never
logged, never shipped to the frontend). DAHITI id 2 = "Victoria, Lake" (verified 2026-10-21).

Usage:  set DAHITI_API_KEY first, then  python 05_prefetch_dahiti.py
"""
import datetime as dt
import json
import os
import sys

import requests

from prep_common import SERIES, log, setup_logging, update_registry

URL = "https://dahiti.dgfi.tum.de/api/v2/download-water-level/"
DAHITI_ID = 2


def main():
    setup_logging()
    key = os.environ.get("DAHITI_API_KEY")
    if not key:
        sys.exit("DAHITI_API_KEY is not set. Rotate the old key on your DAHITI profile, then: "
                 "set DAHITI_API_KEY=<new key>  (PowerShell: $env:DAHITI_API_KEY='...')")
    r = requests.post(URL, json={"api_key": key, "dahiti_id": DAHITI_ID, "format": "json"}, timeout=300)
    r.raise_for_status()
    d = r.json()
    if "data" not in d:
        sys.exit(f"Unexpected DAHITI response: keys {list(d)[:8]}")
    pts = [{"date": p["datetime"][:10], "wse": p["wse"], "u": p.get("wse_u")} for p in d["data"]]
    out = {
        "target": d.get("target_name", "Victoria, Lake"), "dahiti_id": DAHITI_ID,
        "units": "m (water surface elevation)", "n": len(pts),
        "fetched": dt.date.today().isoformat(),
        "source": "DAHITI, DGFI-TUM", "url": d.get("url", f"https://dahiti.dgfi.tum.de/{DAHITI_ID}/"),
        "citation": "Schwatke et al. (2015), Hydrol. Earth Syst. Sci. 19:4345-4364",
        "data": pts,
    }
    (SERIES / "lake_level.json").write_text(json.dumps(out), encoding="utf-8")
    log.info("lake_level.json: %d points, %s -> %s", len(pts), pts[0]["date"], pts[-1]["date"])
    update_registry("lake_level", {
        "title": "Lake water level (satellite altimetry)", "group": "Water", "type": "timeseries-point",
        "urls": {"series": "series/lake_level.json", "click_target": "vectors/lake.geojson"},
        "source": "DAHITI (DGFI-TUM), multi-mission altimetry", "period": f"{pts[0]['date']} to {pts[-1]['date']}",
        "units": "m WSE", "licence": "DAHITI terms: free for scientific use, registration required "
                                      "(review terms before public deployment)",
        "citation": out["citation"]})


if __name__ == "__main__":
    main()
