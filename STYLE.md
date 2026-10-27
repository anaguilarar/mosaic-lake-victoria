# basin_app brand style — extracted from the MOSAIC website

Source: https://mosaic-mfl.github.io/website/ (live Astro build, fetched 2026-10-21; no local repo
was found on this machine). Stylesheets read: `/website/_astro/index.DvvlCefd.css` and
`/website/_astro/about.9PfZ-2qu.css`. Tokens live in `site/css/tokens.css`; this file records origins.

## Colour tokens

| Token | Value | Origin (site custom property) |
|---|---|---|
| `--mosaic-teal` | #0D5C6B | `--color-primary` / `--color-cgiar-teal` (both CSS files) |
| `--mosaic-teal-mid` | #117A8D | `--color-secondary` / `--color-green-mid` |
| `--mosaic-teal-dark` | #0A4753 | `--color-cgiar-teal-dark` (header bottom border) |
| `--mosaic-teal-light` | #D6EEF2 | `--color-accent-light` / `--color-cgiar-teal-light` |
| `--mosaic-bookend` | #085A75 | `--color-bookend`: `.site-header` and `.site-footer` background |
| `--mosaic-sand` | #F7F4EF | `--color-bg` (light) / `--color-cream` |
| `--mosaic-ink` | #1C2B3A | `--color-text` (light) / `--mosaic-ink` |
| `--mosaic-grey` | #6B7A85 | `--color-muted` (light) / `--mosaic-grey` |
| `--mosaic-border` | #E2E0D9 | `--color-border` (light) |
| `--mosaic-amber` | #C97D1B | `--color-amber` / `--mosaic-amber` |
| `--mosaic-earth` | #B54D2F | `--color-earth` (terracotta) |

The site also ships a dark theme (`--color-bg:#0F1A24`, surface #16242F, border #26414C, muted
#9DB0B8); the app uses the light theme only (panels float over satellite imagery).

## Type, spacing, radius, shadows

- Titles: `Georgia, "Times New Roman", "Noto Serif", serif` (`--font-title`); body:
  `Calibri, Candara, "Segoe UI", …` (`--font-body`); mono: IBM Plex Mono (`--font-mono`).
- Type scale `--text-xs … --text-4xl` (0.75–2.25 rem); spacing `--space-1 … --space-16` (4 px base);
- Radii `--radius-sm/md/lg/card/full` = 4/8/12/16 px/pill. Buttons: `.btn` 8 px radius, 600 weight,
  2 px border; primary = filled `--color-green-dark` (#0D5C6B) with white text.
- Shadows: cards `0 10px 30px rgba(28,43,58,.08)`; header `0 1px 12px rgba(0,0,0,.18)`.
- Header: `.site-header` — background `--color-bookend` #085A75, `border-bottom: 3px solid
  --mosaic-teal-dark`, sticky, white nav text; footer same bookend colour.

## Status tags (dataset cards, about.css `.badge-*` / `.status-*` / `.access-*`)

Pill: `padding .22rem .6rem; border-radius 9999px; font-size .72rem; weight 600`. Pairs used in the app:

| App label | Site class adopted | bg / ink |
|---|---|---|
| placeholder (synthetic flood) | `.access-restricted` | #F7E4DD / #B54D2F |
| provisional (latest CHIRPS months) | `.badge-review` (under review) | #FEF3C7 / #92400E |
| not fetched / not built / pending | `.badge-raw` | #ECEAE3 / #6B7A85 |
| live/ok (reserved) | `.badge-validated` | #D6EEF2 / #0D5C6B |

## Logos

- `site/assets/brand/mosaic-mark-reverse.svg` and `cgiar-mfl-lockup.png` downloaded from the site
  verbatim (not redrawn). The SVG's own comment states: "Reversed mark for dark backgrounds: Ocean
  Teal tiles become Light Teal; Amber and Terracotta unchanged (MOSAIC Brand Guidelines v1.0)" —
  the only logo-use guidance found; the reverse mark is therefore used only on the dark bookend header.
- Licence line on the site footer: "licensed under CC BY 4.0 unless otherwise stated" — adopted in
  the app's About panel.

## What stayed from the previous (achromatic-ledger) design

Layout (map-first shell, rail, right panels, time bar), the app-screens rules (KPI strips, honest
states, chart rules) and all map **data palettes** (viridis, cividis reversed, magma, BrBG, RdBu, OrRd)
— these are chosen for scientific reading and colour-blind safety, not branding. The former UI accent
#1d5fbf and Geist typography were replaced by the brand tokens above. The lake hydrograph/rivers hue
is now `--mosaic-teal-mid` #117A8D (water data in the brand's water colour, still distinct from every
map palette).

## Contrast checks (WCAG AA, computed 2026-10-21; see prep/work/contrast_check.txt)

All text/control pairs listed there meet 4.5:1 (normal text) or 3:1 (large text/UI): ink on sand 12.6:1,
grey on sand 4.6:1, white on bookend 7.4:1, teal on white 7.3:1, tag pairs 4.6–6.6:1. Text over
satellite imagery always sits on a solid panel (sand/white), never directly on the map.

## DATA_REPORT

The website has no `DATA_REPORT.md` (probed site and GitHub raw, 404). The app therefore ships its own
`basin_app/DATA_REPORT.md`, generated from `data/meta/layers.json`, and links it from the About panel.
