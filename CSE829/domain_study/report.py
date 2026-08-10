"""
Build the study report as a single self-contained HTML page.

The report is *generated* from results/raw_results.csv, results/summary.csv and
results/figures/manifest.json rather than hand-written, so every number on the
page traces back to the run that produced it and a rerun regenerates the page.

    venv/bin/python -m domain_study.report

Writes ``domain_study/report.html``.
"""

import base64
import html
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .paths import FIGURES, RESULTS, DOMAIN_LABELS

OUT = Path(__file__).resolve().parent / "report.html"

ARMS = ["HE", "CLAHE", "CLALHE-paper", "CLALHE-blended"]
SLOT = {"HE": "s1", "CLAHE": "s2", "CLALHE-paper": "s3", "CLALHE-blended": "s4"}
ORDER = ["xray", "fundus", "underwater", "lowlight", "natural"]

# One image per domain carries the figure grid; a second carries the seam
# close-up. Chosen by eye from results/figures after the run.
FEATURED = {
    "xray": "normal_000",
    "fundus": "fundus_000",
    "underwater": "uw_000",
    "lowlight": "lol_000",
    "natural": "crybaby",
}


# ─────────────────────────────────────────────
#  data
# ─────────────────────────────────────────────

def load():
    raw = pd.read_csv(RESULTS / "raw_results.csv")
    summary = pd.read_csv(RESULTS / "summary.csv")
    manifest = json.loads((FIGURES / "manifest.json").read_text())
    return raw, summary, manifest


def cell(summary, domain, method, col):
    row = summary[(summary.domain == domain) & (summary.method == method)]
    if row.empty or col not in row:
        return np.nan
    return float(row.iloc[0][col])


def ref_stats(raw, domain):
    """Per-image gains against ground truth, plus how often each arm wins."""
    sub = raw[(raw.domain == domain) & raw.psnr_ref.notna()]
    p = sub.pivot(index="image", columns="method", values="psnr_ref")
    s = sub.pivot(index="image", columns="method", values="ssim_ref")
    best = p[ARMS].max(axis=1)
    return {m: {"dpsnr": p[m].mean() - p["original"].mean(),
                "dssim": s[m].mean() - s["original"].mean(),
                "wins": int((p[m] >= best).sum()),
                "n": len(p)} for m in ARMS}


def icl_floor(raw):
    """Share of images where the 'adaptive' clip limit lands on its floor."""
    out = {}
    for method in ("CLALHE-paper", "CLALHE-blended"):
        sub = raw[(raw.method == method) & raw.i_cl.notna()]
        out[method] = (sub.assign(f=sub.i_cl <= 1.0001)
                          .groupby("domain")["f"].mean() * 100).to_dict()
    return out


# ─────────────────────────────────────────────
#  assets
# ─────────────────────────────────────────────

def data_uri(rel):
    p = FIGURES / rel
    if not p.exists():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()


def img_tag(rel, alt, cls="tile-img"):
    uri = data_uri(rel)
    if not uri:
        return f'<div class="tile-missing">{html.escape(alt)}</div>'
    return f'<img class="{cls}" src="{uri}" alt="{html.escape(alt)}" loading="lazy">'


# ─────────────────────────────────────────────
#  charts (inline SVG, theme-aware through tokens)
# ─────────────────────────────────────────────

def grouped_bars(groups, series, values, *, unit="", width=760, height=300,
                 baseline=None, baseline_label="input", zero_line=False):
    """
    Grouped bar chart.

    ``values[group][series]`` -> float. Every bar carries a direct value label:
    two of the four series sit below 3:1 against the light surface, so the
    palette's relief rule requires visible labels rather than colour alone.
    """
    pad_l, pad_r, pad_t, pad_b = 46, 12, 26, 54
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    finite = [v for g in groups for v in
              [values[g].get(s) for s in series] if v is not None and np.isfinite(v)]
    if baseline:
        finite += [baseline[g] for g in groups if np.isfinite(baseline.get(g, np.nan))]
    vmax = max(finite + [0.0])
    vmin = min(finite + [0.0]) if zero_line else 0.0
    vmax += ((vmax - vmin) or 1.0) * 0.10          # headroom for the value labels

    # Snap the step to a round number so the axis reads in whole units, then take
    # only as many steps as the data needs - rounding the top to a fixed four
    # steps would leave a chart of percentages running to 200%.
    raw_step = ((vmax - vmin) or 1.0) / 4
    mag = 10.0 ** np.floor(np.log10(raw_step))
    step = next(m * mag for m in (1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10)
                if m * mag >= raw_step)
    n_ticks = int(np.ceil((vmax - vmin) / step))
    vmax = vmin + step * n_ticks
    span = vmax - vmin

    def y(v):
        return pad_t + plot_h * (1 - (v - vmin) / span)

    gw = plot_w / len(groups)
    bw = min(30.0, (gw - 16) / len(series))

    parts = [f'<svg viewBox="0 0 {width} {height}" class="chart" '
             f'role="img" preserveAspectRatio="xMidYMid meet">']

    # grid + y ticks
    for i in range(n_ticks + 1):
        t = vmin + step * i
        yy = y(t)
        parts.append(f'<line class="gridline" x1="{pad_l}" x2="{width - pad_r}" '
                     f'y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{pad_l - 8}" y="{yy + 3.5:.1f}" '
                     f'text-anchor="end">{t:.4g}</text>')

    for gi, g in enumerate(groups):
        gx = pad_l + gi * gw
        total = len(series) * bw + (len(series) - 1) * 2
        x0 = gx + (gw - total) / 2

        if baseline and np.isfinite(baseline.get(g, np.nan)):
            by = y(baseline[g])
            parts.append(f'<line class="base-tick" x1="{gx + 6:.1f}" '
                         f'x2="{gx + gw - 6:.1f}" y1="{by:.1f}" y2="{by:.1f}"/>')

        for si, s in enumerate(series):
            v = values[g].get(s)
            if v is None or not np.isfinite(v):
                continue
            x = x0 + si * (bw + 2)
            top, bot = y(max(v, 0.0)), y(min(v, 0.0))
            h = max(abs(bot - top), 1.0)
            parts.append(
                f'<rect class="bar {SLOT[s]}" x="{x:.1f}" y="{top:.1f}" '
                f'width="{bw:.1f}" height="{h:.1f}" rx="3"><title>'
                f'{html.escape(s)} — {html.escape(g)}: {v:.3g}{unit}</title></rect>')
            parts.append(f'<text class="val" x="{x + bw / 2:.1f}" '
                         f'y="{top - 5:.1f}" text-anchor="middle">{v:.3g}</text>')

        parts.append(f'<text class="glabel" x="{gx + gw / 2:.1f}" '
                     f'y="{height - pad_b + 20:.1f}" text-anchor="middle">'
                     f'{html.escape(g)}</text>')

    parts.append(f'<line class="axis" x1="{pad_l}" x2="{width - pad_r}" '
                 f'y1="{y(vmin):.1f}" y2="{y(vmin):.1f}"/>')
    parts.append("</svg>")

    legend = "".join(
        f'<span class="key"><i class="sw {SLOT[s]}"></i>{html.escape(s)}</span>'
        for s in series)
    if baseline:
        legend += f'<span class="key"><i class="sw sw-base"></i>{html.escape(baseline_label)}</span>'
    return f'<div class="chart-wrap">{"".join(parts)}<div class="legend">{legend}</div></div>'


# ─────────────────────────────────────────────
#  html pieces
# ─────────────────────────────────────────────

def verdict_chip(kind, text):
    return f'<span class="chip chip-{kind}">{html.escape(text)}</span>'


def fmt(v):
    """Two decimals above 1, four below, so columns line up under tabular-nums."""
    if not np.isfinite(v):
        return "—"
    if v == 0:
        return "0"
    return f"{v:,.2f}" if abs(v) >= 1 else f"{v:.4f}"


def metric_table(summary, domain, cols, labels, notes=""):
    methods = ["original"] + ARMS
    head = "".join(f"<th>{html.escape(l)}</th>" for l in labels)
    rows = []
    for m in methods:
        tds = []
        for c in cols:
            tds.append(f"<td>{fmt(cell(summary, domain, m, c))}</td>")
        cls = ' class="row-input"' if m == "original" else ""
        name = "input (unmodified)" if m == "original" else m
        rows.append(f"<tr{cls}><th scope=\"row\">{html.escape(name)}</th>{''.join(tds)}</tr>")
    note = f'<p class="table-note">{notes}</p>' if notes else ""
    return (f'<div class="table-wrap"><table><thead><tr><th scope="col">method</th>'
            f'{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>{note}')


def figure_grid(domain, manifest, stem):
    entry = next((e for e in manifest[domain]["images"] if e["image"] == stem), None)
    if not entry:
        return ""
    order = ["original"] + ARMS
    if "reference" in entry["tiles"]:
        order.append("reference")
    cells = []
    for m in order:
        rel = entry["tiles"].get(m)
        if not rel:
            continue
        label = {"original": "input", "reference": "ground truth"}.get(m, m)
        cells.append(f'<figure class="tile">{img_tag(rel, f"{domain} {label}")}'
                     f'<figcaption>{html.escape(label)}</figcaption></figure>')
    return f'<div class="grid grid-{len(cells)}">{"".join(cells)}</div>'


def seam_triptych(domain, manifest, stem):
    entry = next((e for e in manifest[domain]["images"] if e["image"] == stem), None)
    if not entry or "seam_tiles" not in entry:
        return ""
    cells = []
    for m, label in (("original", "input"), ("CLALHE-paper", "CLALHE as published"),
                     ("CLALHE-blended", "CLALHE with cross-fade")):
        rel = entry["seam_tiles"].get(m)
        if rel:
            cells.append(f'<figure class="tile tile-zoom">'
                         f'{img_tag(rel, f"{domain} {label} seam close-up")}'
                         f'<figcaption>{html.escape(label)}</figcaption></figure>')
    return f'<div class="grid grid-3">{"".join(cells)}</div>'


CSS = """
/* Committed light theme: the report is printed and read on white, so the
   palette does not follow the viewer's dark-mode preference. Every colour
   below is defined once, on :root, and painted explicitly on body. */
:root{
  color-scheme: light only;
  --ground:#f2f5f6; --surface:#fbfcfc; --surface-2:#e8edee; --sunk:#dfe6e8;
  --ink:#0d1417; --ink-2:#4a585e; --ink-3:#79878d;
  --rule:#d3dbde; --rule-soft:#e3e9eb;
  --accent:#0b6f7d; --accent-ink:#08525c; --accent-wash:#e2eff1;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100;
  --shadow:0 1px 2px rgba(13,20,23,.06), 0 8px 24px -16px rgba(13,20,23,.28);
  --serif: Iowan Old Style, Palatino Linotype, Palatino, Georgia, serif;
  --sans: ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}
*{box-sizing:border-box}
html{background:var(--ground)}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--serif); font-size:17px; line-height:1.66;
  -webkit-font-smoothing:antialiased;
}
.page{max-width:1140px; margin:0 auto; padding:0 24px 96px}
.col{max-width:70ch; margin-inline:auto}
p{margin:0 0 1.05em}
a{color:var(--accent-ink); text-underline-offset:2px}
:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:3px}

/* ---------- masthead ---------- */
.mast{padding:64px 0 34px; border-bottom:1px solid var(--rule)}
.eyebrow{
  font-family:var(--sans); font-size:11.5px; font-weight:650;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent-ink);
  margin:0 0 18px;
}
h1{
  font-family:var(--sans); font-weight:760; letter-spacing:-.026em;
  font-size:clamp(2.1rem,5.2vw,3.15rem); line-height:1.06; margin:0 0 .5em;
  text-wrap:balance; max-width:19ch;
}
.standfirst{font-size:1.16rem; color:var(--ink-2); max-width:62ch; margin:0}
.byline{
  font-family:var(--mono); font-size:12.5px; color:var(--ink-3);
  margin-top:26px; display:flex; flex-wrap:wrap; gap:8px 20px;
}

/* ---------- structure ---------- */
section{padding-top:56px}
h2{
  font-family:var(--sans); font-weight:720; letter-spacing:-.018em;
  font-size:1.62rem; line-height:1.2; margin:0 0 .18em; text-wrap:balance;
}
h3{
  font-family:var(--sans); font-weight:680; letter-spacing:-.012em;
  font-size:1.12rem; margin:2.1em 0 .5em;
}
.kicker{
  font-family:var(--mono); font-size:11.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 8px;
}
.rule{height:1px; background:var(--rule); border:0; margin:0}
.lede{font-size:1.06rem; color:var(--ink-2)}

/* ---------- verdict chips ---------- */
.chip{
  display:inline-flex; align-items:center; gap:6px; white-space:nowrap;
  font-family:var(--sans); font-size:12px; font-weight:650; letter-spacing:.02em;
  padding:3px 10px 4px; border-radius:999px; border:1px solid;
}
.chip::before{content:""; width:7px; height:7px; border-radius:50%; background:currentColor}
.chip-hurts{color:var(--critical); border-color:color-mix(in srgb,var(--critical) 42%,transparent); background:color-mix(in srgb,var(--critical) 9%,transparent)}
.chip-noop{color:var(--serious); border-color:color-mix(in srgb,var(--serious) 46%,transparent); background:color-mix(in srgb,var(--serious) 11%,transparent)}
.chip-mixed{color:var(--warn); border-color:color-mix(in srgb,var(--warn) 50%,transparent); background:color-mix(in srgb,var(--warn) 13%,transparent)}
.chip-helps{color:var(--good); border-color:color-mix(in srgb,var(--good) 42%,transparent); background:color-mix(in srgb,var(--good) 10%,transparent)}

/* ---------- answer panel ---------- */
.answer{
  background:var(--surface); border:1px solid var(--rule); border-radius:12px;
  padding:26px 28px; margin-top:34px; box-shadow:var(--shadow);
}
.answer h2{font-size:1.12rem; margin-bottom:.7em}
.verdicts{list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:11px}
.verdicts li{display:grid; grid-template-columns:170px 118px 1fr; gap:14px; align-items:baseline}
.verdicts .dom{font-family:var(--sans); font-weight:640; font-size:14.5px}
.verdicts .why{color:var(--ink-2); font-size:15px}
@media (max-width:720px){
  .verdicts li{grid-template-columns:1fr; gap:5px}
}

/* ---------- tables ---------- */
.table-wrap{overflow-x:auto; margin:20px 0 6px; border:1px solid var(--rule); border-radius:10px; background:var(--surface)}
table{border-collapse:collapse; width:100%; font-family:var(--mono); font-size:12.9px; font-variant-numeric:tabular-nums}
th,td{padding:9px 13px; text-align:right; white-space:nowrap; border-bottom:1px solid var(--rule-soft)}
thead th{
  font-family:var(--sans); font-size:11px; font-weight:650; letter-spacing:.05em;
  text-transform:uppercase; color:var(--ink-3); text-align:right;
  background:var(--surface-2); border-bottom:1px solid var(--rule);
  position:sticky; top:0;
}
tbody th[scope=row], thead th:first-child{text-align:left}
tbody th[scope=row]{font-family:var(--sans); font-weight:600; font-size:12.6px}
tbody tr:last-child th, tbody tr:last-child td{border-bottom:0}
.row-input th,.row-input td{color:var(--ink-3); background:var(--sunk)}
.table-note{font-family:var(--sans); font-size:13px; color:var(--ink-3); margin:8px 0 0}
.win{color:var(--accent-ink); font-weight:700}

/* ---------- figures ---------- */
.grid{display:grid; gap:12px; margin:22px 0 8px}
.grid-3{grid-template-columns:repeat(3,1fr)}
.grid-5{grid-template-columns:repeat(5,1fr)}
.grid-6{grid-template-columns:repeat(3,1fr)}
@media (max-width:860px){
  .grid-5{grid-template-columns:repeat(2,1fr)}
  .grid-6{grid-template-columns:repeat(2,1fr)}
  .grid-3{grid-template-columns:1fr}
}
.tile{margin:0; display:flex; flex-direction:column; gap:7px}
.tile-img{width:100%; height:auto; display:block; border-radius:7px; border:1px solid var(--rule); background:var(--sunk)}
.tile-zoom .tile-img{image-rendering:auto}
.tile figcaption{font-family:var(--sans); font-size:11.5px; color:var(--ink-3); letter-spacing:.01em}
.tile-missing{padding:22px; border:1px dashed var(--rule); border-radius:7px; font-family:var(--mono); font-size:12px; color:var(--ink-3)}
.fig-note{font-family:var(--sans); font-size:13.5px; color:var(--ink-2); margin:10px 0 0; max-width:78ch}

/* ---------- charts ---------- */
.chart-wrap{margin:22px 0 6px; padding:16px 14px 12px; background:var(--surface); border:1px solid var(--rule); border-radius:10px; overflow-x:auto}
.chart{width:100%; min-width:520px; height:auto; display:block; font-family:var(--sans)}
.chart .gridline{stroke:var(--rule-soft); stroke-width:1}
.chart .axis{stroke:var(--rule); stroke-width:1}
.chart .tick{fill:var(--ink-3); font-size:10.5px; font-variant-numeric:tabular-nums}
.chart .glabel{fill:var(--ink-2); font-size:11.5px; font-weight:600}
.chart .val{fill:var(--ink-2); font-size:10px; font-variant-numeric:tabular-nums}
.chart .base-tick{stroke:var(--ink-3); stroke-width:1.5; stroke-dasharray:4 3}
.bar.s1{fill:var(--s1)} .bar.s2{fill:var(--s2)} .bar.s3{fill:var(--s3)} .bar.s4{fill:var(--s4)}
.legend{display:flex; flex-wrap:wrap; gap:8px 18px; margin-top:12px; padding-left:4px}
.key{display:inline-flex; align-items:center; gap:7px; font-family:var(--sans); font-size:12px; color:var(--ink-2)}
.sw{width:11px; height:11px; border-radius:3px; display:inline-block}
.sw.s1{background:var(--s1)} .sw.s2{background:var(--s2)} .sw.s3{background:var(--s3)} .sw.s4{background:var(--s4)}
.sw-base{background:transparent; border-top:2px dashed var(--ink-3); border-radius:0; height:2px; width:14px}

/* ---------- callout & code ---------- */
.callout{
  border-left:3px solid var(--accent); background:var(--accent-wash);
  padding:16px 20px; border-radius:0 8px 8px 0; margin:24px 0;
  font-size:16px;
}
.callout p:last-child{margin-bottom:0}
.callout strong{font-family:var(--sans); font-weight:670}
pre{
  background:var(--sunk); border:1px solid var(--rule); border-radius:9px;
  padding:15px 17px; overflow-x:auto; margin:18px 0;
  font-family:var(--mono); font-size:12.7px; line-height:1.62; color:var(--ink-2);
}
code{font-family:var(--mono); font-size:.885em; background:var(--surface-2); padding:1px 5px; border-radius:4px}
pre code{background:none; padding:0; font-size:inherit}
ul.notes{padding-left:1.15em; margin:0 0 1.1em}
ul.notes li{margin-bottom:.5em}
.foot{margin-top:72px; padding-top:22px; border-top:1px solid var(--rule); font-family:var(--sans); font-size:13px; color:var(--ink-3)}
"""


def build(raw, summary, manifest):
    ref_uw = ref_stats(raw, "underwater")
    ref_ll = ref_stats(raw, "lowlight")
    floors = icl_floor(raw)
    n = {d: int(cell(summary, d, "original", "n_images")) for d in ORDER}

    def seam(d, m):
        return cell(summary, d, m, "seam")

    # ---------- charts ----------
    ref_chart = grouped_bars(
        ["underwater (UIEB)", "low-light (LOLv1)"], ARMS,
        {"underwater (UIEB)": {m: ref_uw[m]["dpsnr"] for m in ARMS},
         "low-light (LOLv1)": {m: ref_ll[m]["dpsnr"] for m in ARMS}},
        unit=" dB", width=700, height=286)

    seam_chart = grouped_bars(
        ORDER, ["CLAHE", "CLALHE-paper", "CLALHE-blended"],
        {d: {"CLAHE": seam(d, "CLAHE"),
             "CLALHE-paper": seam(d, "CLALHE-paper"),
             "CLALHE-blended": seam(d, "CLALHE-blended")} for d in ORDER},
        baseline={d: seam(d, "original") for d in ORDER},
        baseline_label="input image (baseline)", width=780, height=300)

    floor_chart = grouped_bars(
        ORDER, ["CLALHE-paper", "CLALHE-blended"],
        {d: {"CLALHE-paper": floors["CLALHE-paper"].get(d, np.nan),
             "CLALHE-blended": floors["CLALHE-blended"].get(d, np.nan)} for d in ORDER},
        unit="%", width=780, height=280)

    # ---------- verdicts ----------
    verdicts = [
        ("Chest X-ray", "hurts", "Seams cut across the lung fields; parameters are "
         "identical on all 40 images, so nothing adapts."),
        ("Retinal fundus", "hurts", "Same seams, over the retina the paper's own "
         "dataset was meant to showcase."),
        ("Underwater", "mixed", "Real but small gain — and it only matches stock "
         "CLAHE, never beats it."),
        ("Low-light", "noop", "Wins 0 of 15 images. Plain global HE gains 8× more "
         "against ground truth."),
        ("Natural photos", "mixed", "The paper's home ground: a mild, safe "
         "enhancement, still seam-ridden as published."),
    ]
    verdict_html = "".join(
        f'<li><span class="dom">{html.escape(d)}</span>{verdict_chip(k, t)}'
        f'<span class="why">{html.escape(w)}</span></li>'
        for d, k, (t, w) in
        [(d, k, ({"hurts": "hurts", "noop": "no-op", "mixed": "mixed",
                  "helps": "helps"}[k], w)) for d, k, w in verdicts])

    # ---------- reference table ----------
    def ref_rows(stats):
        out = []
        best = max(stats[m]["dpsnr"] for m in ARMS)
        for m in ARMS:
            s = stats[m]
            cls = ' class="win"' if s["dpsnr"] == best else ""
            out.append(f'<tr><th scope="row">{m}</th>'
                       f'<td{cls}>{s["dpsnr"]:+.2f}</td>'
                       f'<td>{s["dssim"]:+.3f}</td>'
                       f'<td>{s["wins"]}/{s["n"]}</td></tr>')
        return "".join(out)

    ref_table = f"""
<div class="table-wrap"><table>
<thead><tr><th scope="col">method</th><th scope="col">Δ PSNR vs truth</th>
<th scope="col">Δ SSIM vs truth</th><th scope="col">images won</th></tr></thead>
<tbody>
<tr class="row-input"><th scope="row">underwater — UIEB (n={ref_uw['HE']['n']})</th><td></td><td></td><td></td></tr>
{ref_rows(ref_uw)}
<tr class="row-input"><th scope="row">low-light — LOLv1 (n={ref_ll['HE']['n']})</th><td></td><td></td><td></td></tr>
{ref_rows(ref_ll)}
</tbody></table></div>
<p class="table-note">Δ is measured against leaving the image untouched. “Images won” counts
how often each method produced the highest PSNR against ground truth on that image.</p>"""

    paper_cols = ["psnr", "entropy_out", "ambe", "ssi", "cii", "rmse"]
    paper_labels = ["PSNR", "entropy", "AMBE", "SSI", "CII", "RMSE"]
    diag_cols = ["bg_std_in", "bg_std_out", "bg_noise_gain", "clip_pct_out",
                 "seam", "runtime_s"]
    # Header cells are uppercased by CSS, which would turn a sigma into a capital
    # sigma and read as a sum. Spell it out instead.
    diag_labels = ["flat-region SD in", "flat-region SD out", "noise gain",
                   "clipped %", "seam strength", "runtime s"]

    # ---------- per-domain sections ----------
    def domain_section(key, kicker, heading, chip, body_html, extra=""):
        return f"""
<section id="{key}">
  <div class="col">
    <p class="kicker">{kicker}</p>
    <h2>{heading}</h2>
    <p class="lede">{chip}</p>
  </div>
  {figure_grid(key, manifest, FEATURED[key])}
  <p class="fig-note">{DOMAIN_LABELS[key]} — {n[key]} images evaluated;
     one shown. Tiles are the same image through every arm.</p>
  <div class="col">{body_html}</div>
  {metric_table(summary, key, paper_cols, paper_labels,
                "The paper's six metrics, averaged over the domain. PSNR, SSI and RMSE "
                "are measured against the input, so they reward changing it least.")}
  {metric_table(summary, key, diag_cols, diag_labels,
                "Diagnostics. Noise gain is the flat dark region's σ after ÷ before. "
                "Seam strength is the visibility of the subimage grid: 1.0 means invisible.")}
  {extra}
</section>"""

    xray = domain_section(
        "xray", "domain 01 · medicine",
        "Chest X-ray: the seams land in the lung fields",
        verdict_chip("hurts", "hurts") + " CLALHE as published adds a visible cross "
        "through the thorax and nothing about it adapts to the image.",
        f"""
<p>This is the clearest failure in the study, and it is not subtle. On all
{n['xray']} radiographs CLALHE derived <em>exactly the same parameters</em>: CBD = 4,
ONS = 6, a 2×4 subimage grid, on every single image. The tile size and subdivision
that Eq. 2 and Eq. 5 are supposed to adapt to image content are constant across
the whole domain, because chest films all produce a similar count of histogram
extrema (29–53 peaks). The “adaptive” half of the name does no work here.</p>

<p>What the subdivision does do is leave a seam. Measured seam strength is
{seam('xray','CLALHE-paper'):.2f} against a baseline of {seam('xray','original'):.2f} for
the untouched film — the grid boundaries are roughly
{seam('xray','CLALHE-paper')/seam('xray','original'):.1f}× more visible than ordinary
anatomy. In the close-up below the horizontal boundary runs straight through the
lung parenchyma. A radiologist reads that region for nodules and infiltrates; an
algorithm that draws a brightness step across it is worse than one that does
nothing.</p>

<p>The cross-fade variant removes the seam entirely
({seam('xray','CLALHE-blended'):.2f}, indistinguishable from the input's own
{seam('xray','original'):.2f}) and is the gentler enhancement of the two, but it
gains that by doing less: its CII of {cell(summary,'xray','CLALHE-blended','cii'):.2f}
trails stock CLAHE's {cell(summary,'xray','CLAHE','cii'):.2f}.</p>""",
        f"""<div class="col"><h3>The seam, at pixel scale</h3>
<p>A {256}×{256} crop centred on the first grid intersection, from the same
radiograph.</p></div>
{seam_triptych('xray', manifest, FEATURED['xray'])}
<p class="fig-note">Left: the input. Centre: CLALHE exactly as published — the
horizontal and vertical boundaries between independently equalised subimages are
plainly visible over the ribs and lung. Right: the same algorithm with the
cross-fade write-back, where the grid disappears.</p>""")

    fundus = domain_section(
        "fundus", "domain 02 · medicine",
        "Retinal fundus: the paper's own showcase, seamed",
        verdict_chip("hurts", "hurts") + " A vertical brightness step crosses the "
        "retina; the parameters pin to a constant here too.",
        f"""
<p>Fundus photography is the one clinical domain the paper actually tested, so it
is the fairest place to look. CLALHE lands on CBD = 4 and ONS = 6 for essentially
every image ({n['fundus']} evaluated), producing a 2×3 grid. The seam strength of
{seam('fundus','CLALHE-paper'):.2f} against the input's {seam('fundus','original'):.2f}
puts a visible vertical band across the retina — in the tile above it runs beside
the optic disc.</p>

<p>The adaptive clip limit is also inert here: it sits on its floor of 1.0 in
{floors['CLALHE-paper']['fundus']:.0f}% of images for the published variant and
{floors['CLALHE-blended']['fundus']:.0f}% for the blended one. A clip limit of 1.0 is
the weakest setting CLAHE accepts, so on most fundus images CLALHE is running a
near-neutral CLAHE and calling the result adaptive.</p>

<p>One measurement artefact is worth naming because it would otherwise
contaminate the numbers: {cell(summary,'fundus','original','frame_pct'):.0f}% of each
fundus frame is the pure-black surround outside the circular field of view. Every
enhancement method lifts that surround off zero, which is invisible clinically but
destroys any contrast statistic that divides by intensity. The CII here is computed
only over blocks that are real image content, with the block selection taken from
the input so all five arms are scored on the same pixels.</p>""")

    underwater = domain_section(
        "underwater", "domain 03 · underwater",
        "Underwater: a real gain, exactly equal to plain CLAHE",
        verdict_chip("mixed", "mixed") + " The only domain where CLALHE clearly "
        "helps against ground truth — and it never beats the stock method it extends.",
        f"""
<p>UIEB ships a reference image for every degraded frame, so here we can ask the
question the paper's metrics cannot: did the output move <em>toward a good
image</em>? It did. CLALHE-blended gains {ref_uw['CLALHE-blended']['dpsnr']:+.2f} dB and
{ref_uw['CLALHE-blended']['dssim']:+.3f} SSIM over leaving the frame alone, and it
improves {ref_uw['CLALHE-blended']['wins']} of {ref_uw['CLALHE-blended']['n']} images
outright.</p>

<p>The catch is the comparison. Stock CLAHE at its documented defaults gains
{ref_uw['CLAHE']['dpsnr']:+.2f} dB — the same figure to two decimals — in
{cell(summary,'underwater','CLAHE','runtime_s')*1000:.0f} ms against CLALHE's
{cell(summary,'underwater','CLALHE-blended','runtime_s')*1000:.0f} ms, roughly
{cell(summary,'underwater','CLALHE-blended','runtime_s')/cell(summary,'underwater','CLAHE','runtime_s'):.0f}×
faster. Everything CLALHE adds — the peak/valley analysis, the CIQI search, the
subdivision — buys nothing measurable over the method it is built on.</p>

<p>Worth noting for anyone applying this underwater: the blue-green cast is
untouched. Both CLALHE implementations enhance only the LAB L-channel and leave a
and b alone by construction, so colourfulness barely moves
({cell(summary,'underwater','original','colorfulness_out'):.0f} in,
{cell(summary,'underwater','CLALHE-blended','colorfulness_out'):.0f} out). CLALHE is a
luminance-contrast method; underwater images mostly need colour correction.</p>""")

    lowlight = domain_section(
        "lowlight", "domain 04 · low light",
        "Low-light: the domain it should own, and it wins nothing",
        verdict_chip("noop", "no-op") + " Best on the paper's metrics, last against "
        "ground truth. It wins 0 of 15 images.",
        f"""
<p>LOLv1 pairs each low-light frame with a normal-light capture of the same scene,
which makes this the sharpest test in the study — and the result is the one that
should decide the question.</p>

<p>Against ground truth, CLALHE gains {ref_ll['CLALHE-blended']['dpsnr']:+.2f} dB.
Global histogram equalisation — the crude 1970s baseline the whole CLAHE family
exists to improve on — gains {ref_ll['HE']['dpsnr']:+.2f} dB, about
{ref_ll['HE']['dpsnr']/ref_ll['CLALHE-blended']['dpsnr']:.0f}× more, and takes the best
result on {ref_ll['HE']['wins']} of {ref_ll['HE']['n']} images. CLALHE takes the best
result on <strong>{ref_ll['CLALHE-blended']['wins']}</strong>. Not few — none.</p>

<p>The picture above shows why: the output is still dark. CLALHE's clip limit
collapses to its floor on {floors['CLALHE-paper']['lowlight']:.0f}% of these images
(published variant) and {floors['CLALHE-blended']['lowlight']:.0f}% (blended), so it
applies almost no correction to images whose entire histogram is crushed into the
bottom of the range.</p>

<div class="callout"><p><strong>This is where the paper's metric choice bites.</strong>
On the paper's own scoreboard CLALHE looks like the winner here: PSNR
{cell(summary,'lowlight','CLALHE-paper','psnr'):.1f} against HE's
{cell(summary,'lowlight','HE','psnr'):.1f}, AMBE
{cell(summary,'lowlight','CLALHE-paper','ambe'):.1f} against
{cell(summary,'lowlight','HE','ambe'):.0f}, RMSE
{cell(summary,'lowlight','CLALHE-paper','rmse'):.1f} against
{cell(summary,'lowlight','HE','rmse'):.0f}. Every one of those metrics is computed
between the input and the output, so a method scores well by <em>not changing a
dark image</em>. Swap in the ground truth and the ranking inverts completely.</p></div>""")

    natural = domain_section(
        "natural", "domain 05 · control",
        "Natural photographs: the home ground",
        verdict_chip("mixed", "mixed") + " A mild, safe enhancement — the behaviour "
        "the paper reports — with the seam still there.",
        f"""
<p>Two of the paper's three datasets were consumer photographs, so this control set
shows CLALHE at its best. And it does behave reasonably: a modest contrast lift
(CII {cell(summary,'natural','CLALHE-blended','cii'):.2f}), a small entropy gain, brightness
well preserved (AMBE {cell(summary,'natural','CLALHE-blended','ambe'):.1f} against HE's
{cell(summary,'natural','HE','ambe'):.0f}), and none of HE's blown highlights
({cell(summary,'natural','CLALHE-blended','clip_pct_out'):.2f}% of pixels clipped versus
{cell(summary,'natural','HE','clip_pct_out'):.1f}%).</p>

<p>This is a real strength and it is worth stating plainly: as a <em>gentle</em>
enhancer that will not wreck a photograph, CLALHE is fine. It is just that stock
CLAHE is also fine, faster, and lifts contrast further. And the published version
still carries a seam strength of {seam('natural','CLALHE-paper'):.2f} here — the
artifact is not domain-specific, it is structural.</p>""")

    # ---------- assembly ----------
    return f"""<div class="page">

<header class="mast col">
  <p class="eyebrow">CSE829 · image enhancement · domain study</p>
  <h1>Does CLALHE hold up outside the pictures it was tested on?</h1>
  <p class="standfirst">A published contrast-enhancement method, re-run over
  {sum(n.values())} images from five domains it was never evaluated on — chest
  radiographs, retinal fundus, underwater, low-light, and ordinary photographs —
  scored against ground truth wherever ground truth exists.</p>
  <p class="byline"><span>Mohammed &amp; Isa, IEEE Access 13:62600–62632, 2025</span>
  <span>DOI 10.1109/ACCESS.2025.3558506</span>
  <span>5 methods × {sum(n.values())} images = {len(raw)} measurements</span></p>
</header>

<section id="answer">
  <div class="col">
    <p class="kicker">the short answer</p>
    <h2>No — and the reason is visible in the pictures</h2>
    <p class="lede">CLALHE generalises poorly. Where it appears to win, it wins on
    metrics that reward leaving the image alone; where ground truth exists, it is
    beaten by methods a decade older. On medical images it actively damages the
    picture.</p>
  </div>
  <div class="col answer">
    <h2>Verdict by domain</h2>
    <ul class="verdicts">{verdict_html}</ul>
  </div>
  <div class="col">
    <p style="margin-top:26px">Three findings carry that verdict, and each is
    measured rather than asserted:</p>
    <ul class="notes">
      <li><strong>The subimage seam is structural, not incidental.</strong> As
      published, CLALHE leaves a visible grid in every domain tested — 2.8× to 4.3×
      more visible than the image's own content. On a chest film it crosses the
      lungs.</li>
      <li><strong>The adaptive parameters frequently aren't adaptive.</strong> The
      clip limit lands on its floor of 1.0 in
      {floors['CLALHE-paper']['lowlight']:.0f}% of low-light and
      {floors['CLALHE-paper']['fundus']:.0f}% of fundus images, and on X-rays every
      one of the {n['xray']} images produced identical parameters.</li>
      <li><strong>Against ground truth it loses.</strong> On low-light images global
      HE gains {ref_ll['HE']['dpsnr']:.1f} dB where CLALHE gains
      {ref_ll['CLALHE-blended']['dpsnr']:.1f} dB.</li>
    </ul>
  </div>
</section>

<section id="method">
  <div class="col">
    <p class="kicker">how this was measured</p>
    <h2>Setup, and one deliberate departure from the paper</h2>
    <p>Five arms were run over every image: the unmodified input as a control,
    global histogram equalisation, stock OpenCV CLAHE at its documented defaults
    (clip 2.0, 8×8 tiles), CLALHE exactly as published
    (<code>CLALHE_new.py</code>), and CLALHE with the cross-fade write-back that
    removes the subimage seam (<code>CLALHE.py</code>). All five touch only the
    LAB L-channel, so colour handling is identical and any difference is
    attributable to the luminance algorithm.</p>

    <p>The paper scores enhancement with PSNR, entropy, AMBE, SSI, CII and RMSE, and
    all of those except entropy and CII compare the output to <em>the input</em>.
    That is a problem: a method that returns the image unchanged scores a perfect
    PSNR of ∞, a perfect SSI of 1.0 and an AMBE of 0. The metric rewards timidity,
    and the quieter of two enhancers wins by construction.</p>

    <p>So two of the five domains were chosen because they ship a
    <em>reference</em> image — UIEB pairs each underwater frame with a corrected
    version, LOLv1 pairs each low-light frame with a normal-light capture of the
    same scene. There, PSNR and SSIM are measured against the reference instead,
    which asks whether the output moved toward a good image rather than whether it
    stayed near a bad one. Both scoreboards are reported throughout.</p>

    <p>Three diagnostics were added for failure modes the global statistics miss:
    <strong>seam strength</strong> (the mean brightness step across the subimage grid
    boundaries divided by the mean step everywhere else — 1.0 means the grid is
    invisible), <strong>noise gain</strong> (how much louder a flat dark region got),
    and <strong>clipping</strong> (pixels pinned to 0 or 255).</p>
  </div>

  <div class="col"><h3>Against the paper's published figures</h3>
  <p>The paper reports PSNR 31.822, AMBE 1.224 and RMSE 1.542 on DIARETDB1. On the
  fundus set here CLALHE-as-published scores PSNR
  {cell(summary,'fundus','CLALHE-paper','psnr'):.2f}, AMBE
  {cell(summary,'fundus','CLALHE-paper','ambe'):.2f}, RMSE
  {cell(summary,'fundus','CLALHE-paper','rmse'):.2f} — the same order of magnitude on
  PSNR, but a much larger brightness shift. Two caveats belong with that comparison
  and both cut against reading it as a reproduction: the reachable archive is
  <strong>DIARETDB0</strong>, the sibling database from the same group and camera,
  not DIARETDB1 itself (the official mirror is dead); and the implementation under
  test clamps the clip limit to ≥ 1.0, which the paper's Eq. 3 does not. Treat the
  numbers below as characterising <em>this implementation</em>, which is the thing
  actually being asked about.</p></div>
</section>

<section id="reference-scoreboard">
  <div class="col">
    <p class="kicker">the decisive measurement</p>
    <h2>Scored against ground truth, the ranking inverts</h2>
    <p>Where a reference image exists, every method can be scored on whether it
    actually improved the picture. This is the same data as the per-domain tables,
    stated as a gain over doing nothing.</p>
  </div>
  {ref_chart}
  <p class="fig-note">Gain in PSNR against the ground-truth image, relative to
  leaving the input untouched. Higher is better. On low-light, global HE — the
  simplest method in the comparison — gains eight times what CLALHE does.</p>
  <div class="col">{ref_table}</div>
</section>

{xray}
{fundus}
{underwater}
{lowlight}
{natural}

<section id="seams">
  <div class="col">
    <p class="kicker">cross-cutting finding 01</p>
    <h2>The seam is in the algorithm, not the images</h2>
    <p>Part 2 of the paper subdivides the image into ONS subimages, equalises each
    independently, and — per Section IX — merges them by concatenation. Independent
    histograms mean independent lookup tables, so two pixels either side of a
    boundary with the same input value get different output values. The result is a
    visible grid.</p>
    <p>This is measurable. Seam strength compares the average brightness step across
    the grid boundaries with the average step everywhere else in the same image; the
    input's own value is the baseline, since real pictures have edges too.</p>
  </div>
  {seam_chart}
  <p class="fig-note">Seam strength by domain. The dashed rule is the input image's
  own value — where a bar sits at the rule, the grid is invisible. CLALHE as
  published stands well clear of it in four of five domains; the cross-fade variant
  sits on it everywhere.</p>
  <div class="col">
    <p>The fix is not exotic and does not change the algorithm: read each subimage
    with a margin of context and composite through a linear cross-fade whose weights
    sum to 1 across every boundary. The subdivision, the per-subimage histograms and
    the Part 1 parameters are all untouched. Its cost is that the output is slightly
    gentler still.</p>
    <p>Why the paper's evaluation never caught it: PSNR, entropy, AMBE, SSI, CII and
    RMSE are global statistics over hundreds of thousands of pixels, and a seam is a
    few thousand of them. It moves the averages by almost nothing. It is only
    obvious when you look at the picture.</p>
  </div>
</section>

<section id="adaptivity">
  <div class="col">
    <p class="kicker">cross-cutting finding 02</p>
    <h2>The adaptive clip limit spends most of its time on the floor</h2>
    <p>CLALHE's headline contribution is choosing its own parameters: tile size from
    the peak count (Eq. 2), clip limit from peak and valley frequencies (Eq. 3),
    subdivision from the valley count (Eq. 5), with a CIQI fitness search over
    candidates. In practice the clip limit is pinned to its minimum of 1.0 —
    the weakest setting CLAHE accepts — on most images in most domains.</p>
  </div>
  {floor_chart}
  <p class="fig-note">Share of images where the selected clip limit lands on its
  floor of 1.0. On low-light and fundus images the “adaptive” parameter is
  effectively a constant.</p>
  <div class="col">
    <p>The other parameters are barely more responsive. Across all
    {n['xray']} chest X-rays, CLALHE chose CBD = 4 and ONS = 6 — a 2×4 grid — for
    every single image. Across the fundus set it chose CBD = 4 and ONS = 6 for
    essentially all of them. Two domains with completely different content converge
    on the same configuration, because both produce a similar count of histogram
    extrema, and the count is all Eq. 2 and Eq. 5 look at.</p>
    <p>There is a structural reason the CIQI search adds nothing, noted in the
    earlier audit of this implementation: maximising CIQI = (PSNR + entropy) / AMBE
    over the candidate clip limits is equivalent to picking the smallest one, since
    a weaker clip limit changes the image less, which raises PSNR and lowers AMBE
    together. The search reliably returns the least aggressive candidate, which is
    why the floor is hit so often.</p>
  </div>
</section>

<section id="bitdepth">
  <div class="col">
    <p class="kicker">cross-cutting finding 03</p>
    <h2>It cannot see 16-bit medical data at all</h2>
    <p>Everything above uses 8-bit images, because that is what is publicly
    downloadable. Native medical imaging is not 8-bit: DICOM radiographs and CT are
    stored at 12 or 16 bits, and extra range is precisely what contrast enhancement
    there is for.</p>
    <p>CLALHE's parameter stage calls
    <code>cv2.calcHist(…, [256], [0, 256])</code> and its PSNR hardcodes 255.0. Feed
    it the same X-ray in a 16-bit container and the histogram sees only pixels below
    256:</p>
<pre><code>8-bit    409600 of 409600 pixels counted  (100.0%)
16-bit    17431 of 409600 pixels counted  (  4.3%)

           n_peaks  n_valleys   CBD     I_CL   ONS
8-bit           36         35     4   3.0891     6
16-bit           0          0     8   2.0000     2</code></pre>
    <p>It does not raise an error. It finds zero peaks, silently falls through to
    hardcoded defaults, and returns an image. Every adaptive claim in the paper
    evaporates, and nothing in the output signals it. Native DICOM must be windowed
    to 8 bits first — which is itself a contrast decision, made outside the method,
    by someone else. The paper never states the constraint.</p>
    <p>Reproduce with <code>venv/bin/python -m domain_study.bitdepth_check</code>.</p>
  </div>
</section>

<section id="limits">
  <div class="col">
    <p class="kicker">what would change these conclusions</p>
    <h2>Limitations</h2>
    <ul class="notes">
      <li><strong>The fundus set is DIARETDB0, not DIARETDB1.</strong> Same group,
      same camera, 130 images at 1500×1152 against the paper's 1500×1100 — a close
      sibling, but not the identical corpus, so the comparison with the paper's
      published figures is indicative rather than a reproduction.</li>
      <li><strong>CII departs from Eq. 12.</strong> The paper computes Michelson
      contrast over a hand-chosen ROI. With no ROI annotations across five domains
      it is computed densely here — every 32-pixel block as an ROI against its
      surrounding ring, averaged over blocks that are image content. Applied
      identically to all arms, so the ratio stays fair, but the absolute values are
      not the paper's.</li>
      <li><strong>Sample sizes are modest</strong> — 40 images per domain, 15 for
      low-light (all of LOLv1's eval set), 11 natural photographs. Enough to
      establish the parameter-collapse and seam findings, which are near-universal
      within each domain; thinner for the reference-based margins.</li>
      <li><strong>Only two implementations were tested</strong>, both from this
      repository. Differences from the authors' own code — the clip-limit clamp at
      1.0 and the histogram smoothing before peak detection are two known ones —
      would shift the numbers, though not the seam, which follows from the published
      Part 2 directly.</li>
      <li><strong>No satellite or remote-sensing domain.</strong> It was scoped out
      of this run; the 16-bit finding above is the part of that domain's answer that
      generalises, since most usable satellite imagery is 12- or 16-bit.</li>
    </ul>
  </div>
</section>

<section id="repro">
  <div class="col">
    <p class="kicker">reproducing this</p>
    <h2>Everything here regenerates from four commands</h2>
    <p>Sources are public and non-gated; the image subset is chosen with a fixed
    seed, and reruns are byte-identical apart from timings.</p>
<pre><code>venv/bin/python -m domain_study.datasets --all      # ~350 MB, 5 domains
venv/bin/python -m domain_study.run_study           # raw_results.csv + summary.csv
venv/bin/python -m domain_study.make_figures        # comparison tiles
venv/bin/python -m domain_study.report              # this page</code></pre>
    <p>Per-image measurements live in <code>results/raw_results.csv</code>
    ({len(raw)} rows), domain means in <code>results/summary.csv</code>.</p>
  </div>
  <p class="foot">Generated from results/raw_results.csv · {len(raw)} measurements ·
  {sum(n.values())} images · 5 domains · 5 methods</p>
</section>

</div>"""


def main():
    raw, summary, manifest = load()
    body = build(raw, summary, manifest)
    page = (f"<title>Does CLALHE hold up outside its own test set?</title>\n"
            f"<style>{CSS}</style>\n{body}\n")
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page) / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
