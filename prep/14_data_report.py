"""Merge layer metadata from data/meta/layers.json into basin_app/DATA_REPORT.md.

MERGE, never regenerate: content outside the per-layer marker pairs
    <!-- auto:layer:<id> start --> ... <!-- auto:layer:<id> end -->
is user-owned (Methods, study justifications, References) and is never touched.
Rules:
  - a layer whose markers exist        -> the block between them is refreshed;
  - a layer with a manual "## <title>" heading but no markers (user-edited) -> left alone;
  - a new layer (no markers, no heading) -> appended, wrapped in markers;
  - the Sentinel-2 entry is always treated as manual (stays as-is until the export is confirmed).

Usage:  python prep/14_data_report.py
"""
import datetime as dt
import json
import re

from prep_common import APP, META, log, setup_logging

# Only these ids are generator-managed (their marker blocks + the table rows + auto:ref entries).
# Everything else in DATA_REPORT.md is user-owned prose and is never touched or appended.
MANAGED_IDS = {"landcover", "worldcover", "fire", "burned_area"}


def section_body(l):
    lines = []
    for key, label in [("source", "Source"), ("period", "Period"), ("units", "Units"),
                       ("licence", "Licence"), ("citation", "Citation"), ("caveats", "Caveats"),
                       ("release_note", "Release note")]:
        if l.get(key):
            lines.append(f"- **{label}:** {l[key]}")
    if l.get("placeholder"):
        lines.append("- **Status:** PLACEHOLDER (synthetic) until the Copernicus GFM run lands.")
    return "\n".join(lines)


def main():
    setup_logging()
    reg = json.loads((META / "layers.json").read_text(encoding="utf-8"))
    out = APP / "DATA_REPORT.md"
    text = out.read_text(encoding="utf-8") if out.exists() else (
        "# Lake Victoria Basin Explorer — data report\n\n"
        f"Created {dt.date.today().isoformat()}. Part of MOSAIC — the CGIAR Multifunctional "
        "Landscapes Science Programme (https://mosaic-mfl.github.io/website/). Content licensed "
        "under CC BY 4.0 unless otherwise stated; each dataset keeps its own licence.\n")

    refreshed, skipped = [], []
    for l in reg["layers"]:
        lid, title = l["id"], l.get("title", l["id"])
        if lid not in MANAGED_IDS:
            skipped.append(lid)                      # user-owned prose: never touched or appended
            continue
        start, end = f"<!-- auto:layer:{lid} start -->", f"<!-- auto:layer:{lid} end -->"
        if start in text and end in text:
            cur = re.search(re.escape(start) + r".*?" + re.escape(end), text, flags=re.S).group(0)
            if "<!-- auto:managed -->" not in cur:
                skipped.append(lid)              # block holds approved prose: left verbatim
                continue
            block = f"{start}\n<!-- auto:managed -->\n**{title}.**\n{section_body(l)}\n{end}"
            text = re.sub(re.escape(start) + r".*?" + re.escape(end), block, text, flags=re.S)
            refreshed.append(lid)
        # no marker pair -> nothing written; the master file decides where blocks live
    out.write_text(text, encoding="utf-8")
    log.info("DATA_REPORT merged: refreshed %s | untouched (user-owned) %d layers", refreshed or "-", len(skipped))


if __name__ == "__main__":
    main()
