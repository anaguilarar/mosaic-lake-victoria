"""P9.0 - static figures for the story tab (data/figures/, PNG + SVG, 2x resolution).

Figures (white background, thin spines, Arial, no chartjunk):
    spi_2019_2026:  SPI-3 side by side, Dec 2019 (the OND 2019 short rains) vs Aug 2026 (latest),
                    from data/climate/app/spi3.tif (int16 = SPI x 100, bands described by month),
                    the app's own BrBG ramp and -3..+3 range (climate.js RAMPS.precip_anom),
                    lake masked (CHIRPS land mask), no basin outline, shared horizontal colourbar.
    sediment_nyando: Humphrey et al. (2025) sediment source apportionment of the Nyando basin
                    (44/39/17 % as printed, abstract p.1 and sect. 3.2 p.5, fig. 5a),
                    horizontal bars with the +/- sd whiskers.

Usage:  python 90_story_figures.py
"""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from prep_common import APP, DATA, log, setup_logging

FIG = DATA / "figures"
plt.rcParams.update({
    "font.family": "Arial", "font.size": 9, "axes.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False,
    "savefig.facecolor": "white", "figure.facecolor": "white",
    "svg.fonttype": "none",
})
INK = "#1C2B3A"


def save(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(FIG / f"{name}.{ext}", dpi=300 if ext == "png" else None,
                    bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    log.info("wrote %s (.png 2x + .svg)", FIG / name)


def spi_band(src, ym):
    return src.descriptions.index(ym) + 1   # bands are described by month ('2019-12')


def fig_spi():
    meta = json.load(open(DATA / "climate" / "app" / "app_meta.json"))
    months = [("2019-12", "SPI-3 · Dec 2019 (OND short rains)"), ("2026-08", "SPI-3 · Aug 2026 (latest, provisional)")]
    w, s_, e, n = meta["bbox"][0], meta["bbox"][1], meta["bbox"][2], meta["bbox"][3]
    fig, axes = plt.subplots(1, 2, figsize=(6.2, 3.0), constrained_layout=True)
    with rasterio.open(DATA / "climate" / "app" / "landmask.tif") as lm:
        land = lm.read(1)
    with rasterio.open(DATA / "climate" / "app" / "spi3.tif") as src:
        for ax, (ym, title) in zip(axes, months):
            a = src.read(spi_band(src, ym)).astype("f4")
            a[a == src.nodata] = np.nan
            a[land == 20] = np.nan                 # lake out (landmask 20 = water): satellite rainfall is less reliable there
            a *= 0.01                              # int16 = SPI x 100, clamped at +/-300
            im = ax.imshow(a, extent=(w, e, s_, n), cmap="BrBG", vmin=-3, vmax=3, interpolation="nearest")
            # no basin outline: the ICPAC boundary is not published (licence not specified)
            ax.set_title(title, fontsize=10, color=INK)
            ax.set_aspect("equal")
            ax.set_xticks([30, 32, 34]); ax.set_yticks([-4, -2, 0])
            ax.tick_params(length=2, labelsize=8.5, colors=INK)
    cb = fig.colorbar(im, ax=axes, orientation="horizontal", shrink=0.55, pad=0.08, aspect=35)
    cb.set_label("SPI-3 (−3 dry  →  +3 wet)", fontsize=9, color=INK)
    cb.ax.tick_params(length=2, labelsize=8.5, colors=INK)
    cb.outline.set_linewidth(0.5)
    save(fig, "spi_2019_2026")


def fig_sediment():
    # as printed in Humphrey et al. (2025): abstract p.1; sect. 3.2 p.5, fig. 5a
    rows = [("Nyando-Kipchorian", 44, 4), ("Ainamutua", 39, 4), ("Awach Kano & Nyaidho", 17, 7)]
    fig, ax = plt.subplots(figsize=(3.6, 1.7), constrained_layout=True)
    y = np.arange(len(rows))[::-1]
    vals = [r[1] for r in rows]; errs = [r[2] for r in rows]
    ax.barh(y, vals, xerr=errs, height=0.62, color=["#0D5C6B", "#117A8D", "#9DB0B8"],
            error_kw=dict(elinewidth=0.8, capsize=2, capthick=0.8, ecolor=INK))
    for yi, v, e in zip(y, vals, errs):
        ax.text(v + e + 1.5, yi, f"{v} ± {e} %", va="center", fontsize=7, color=INK)
    ax.set_yticks(y, [r[0] for r in rows], fontsize=7.5, color=INK)
    ax.set_xlim(0, 60); ax.set_xticks([0, 20, 40, 60])
    ax.set_xlabel("share of the Nyando riverbed-sediment mixture (%)", fontsize=7, color=INK)
    ax.tick_params(length=2, labelsize=6.5, colors=INK)
    save(fig, "sediment_nyando")


if __name__ == "__main__":
    setup_logging()
    FIG.mkdir(parents=True, exist_ok=True)
    fig_spi()
    fig_sediment()
