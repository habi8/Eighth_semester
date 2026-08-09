"""
Driver for the CLALHE domain study.

For every domain x image x method it applies the arm, times it, computes every
applicable metric and records the parameters CLALHE derived, then writes:

    results/raw_results.csv   one row per image x method
    results/summary.csv       per-domain x method means, laid out like the
                              paper's Table 8

Per-image failures are caught and recorded rather than aborting the run, so one
bad file cannot cost a full sweep.

Usage::

    venv/bin/python -m domain_study.run_study            # everything
    venv/bin/python -m domain_study.run_study --domain xray --limit 3
"""

import argparse
import sys
import time
import traceback

import cv2
import numpy as np
import pandas as pd

from . import metrics as M
from .methods import METHODS
from .paths import DOMAINS, RESULTS, ensure_dirs, input_dir, reference_dir

# Columns whose per-domain mean goes into summary.csv, in report order.
SUMMARY_COLS = [
    "psnr", "entropy_out", "d_entropy", "ambe", "ssi", "cii", "rmse",
    "psnr_ref", "ssim_ref",
    "bg_std_in", "bg_std_out", "bg_noise_gain", "frame_pct",
    "clip_pct_out", "seam", "colorfulness_out",
    "n_peaks", "n_valleys", "cbd", "i_cl", "ons", "runtime_s",
]


def _load_pairs(domain, limit=None):
    """Yield (name, input_bgr, reference_bgr_or_None) for a domain."""
    ins = sorted(input_dir(domain).glob("*.png"))
    if limit:
        ins = ins[:limit]
    refs = reference_dir(domain)
    for p in ins:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None:
            print(f"    unreadable: {p.name}")
            continue
        ref = None
        rp = refs / p.name
        if rp.exists():
            ref = cv2.imread(str(rp), cv2.IMREAD_COLOR)
        yield p.name, img, ref


def _check_sanity(row):
    """
    The identity arm pins the metric implementations to known values.

    A deviation here means a metric is wrong, not that a method behaved oddly,
    so it is worth failing loudly the moment it happens.
    """
    problems = []
    if abs(row["psnr"] - 100.0) > 1e-6:
        problems.append(f"psnr={row['psnr']}")
    if abs(row["ssi"] - 1.0) > 1e-6:
        problems.append(f"ssi={row['ssi']}")
    # CII is a ratio guarded by an epsilon, so it lands next to 1.0 rather than
    # exactly on it; the others are exact by construction.
    if abs(row["cii"] - 1.0) > 1e-4:
        problems.append(f"cii={row['cii']}")
    if abs(row["ambe"]) > 1e-9:
        problems.append(f"ambe={row['ambe']}")
    if abs(row["rmse"]) > 1e-9:
        problems.append(f"rmse={row['rmse']}")
    if problems:
        raise AssertionError("identity arm failed sanity check: " + ", ".join(problems))


def run_image(domain, name, img, ref, sanity_done):
    """Apply every arm to one image and return a list of result rows."""
    h, w = img.shape[:2]
    mask = M.flat_dark_mask(img)
    entropy_in = M.entropy(img)
    clip_in = M.clip_fraction(img)
    color_in = M.colorfulness(img)
    std_in = M.bg_std(img, mask)
    frame_pct = 100.0 * float(M.frame_mask(img).mean())

    outputs, rows = {}, []

    for method_name, fn in METHODS:
        row = {"domain": domain, "image": name, "method": method_name,
               "width": w, "height": h, "status": "ok"}
        try:
            t0 = time.perf_counter()
            out, telem = fn(img)
            row["runtime_s"] = time.perf_counter() - t0

            row.update({
                "psnr": M.psnr(img, out),
                "entropy_in": entropy_in,
                "entropy_out": M.entropy(out),
                "ambe": M.ambe(img, out),
                "ssi": M.ssi(img, out),
                "cii": M.cii(img, out),
                "rmse": M.rmse(img, out),
                "bg_std_in": std_in,
                "bg_std_out": M.bg_std(out, mask),
                "bg_noise_gain": M.bg_noise_gain(img, out, mask),
                "frame_pct": frame_pct,
                "clip_pct_in": clip_in,
                "clip_pct_out": M.clip_fraction(out),
                "colorfulness_in": color_in,
                "colorfulness_out": M.colorfulness(out),
            })
            row["d_entropy"] = row["entropy_out"] - entropy_in
            if ref is not None:
                row["psnr_ref"] = M.psnr_ref(out, ref)
                row["ssim_ref"] = M.ssim_ref(out, ref)
            row.update(telem)
            outputs[method_name] = out
        except Exception:
            row["status"] = "failed"
            print(f"    FAILED {domain}/{name} [{method_name}]")
            traceback.print_exc(limit=3)
        rows.append(row)

    # Seam strength is measured on the grid CLALHE-paper actually used, and the
    # same lines are scored for every arm. HE and CLAHE have no grid, so their
    # value is the metric's noise floor for this image - the control that makes
    # the CLALHE numbers interpretable.
    grid = next((r for r in rows if r["method"] == "CLALHE-paper"
                 and r["status"] == "ok"), None)
    if grid is not None:
        args = (grid["sub_h"], grid["sub_w"], grid["grid_rows"], grid["grid_cols"])
        for row in rows:
            if row["status"] == "ok" and row["method"] in outputs:
                row["seam"] = M.seam_strength(outputs[row["method"]], *args)

    if not sanity_done:
        identity = next(r for r in rows if r["method"] == "original")
        _check_sanity(identity)

    return rows


def write_summary(df, raw_name):
    """
    Per-domain x method means, laid out like the paper's Table 8.

    The summary filename is derived from the raw filename so that a partial run
    (``--domain lowlight --out det_a.csv``) can never overwrite the summary of
    a full sweep.
    """
    ok = df[df["status"] == "ok"]
    present = [c for c in SUMMARY_COLS if c in ok.columns]
    summary = (ok.groupby(["domain", "method"], sort=False)[present]
                 .mean(numeric_only=True).round(4).reset_index())
    summary["n_images"] = (ok.groupby(["domain", "method"], sort=False)
                             .size().reset_index(drop=True))
    stem = raw_name[:-4] if raw_name.endswith(".csv") else raw_name
    name = "summary.csv" if stem == "raw_results" else f"{stem}_summary.csv"
    summary.to_csv(RESULTS / name, index=False)
    return RESULTS / name


def main():
    ap = argparse.ArgumentParser(description="Run the CLALHE domain study")
    ap.add_argument("--domain", choices=DOMAINS, action="append",
                    help="restrict to one domain (repeatable)")
    ap.add_argument("--limit", type=int, help="only the first N images per domain")
    ap.add_argument("--out", default="raw_results.csv", help="filename under results/")
    ap.add_argument("--rebuild-summary", action="store_true",
                    help="recompute the summary from an existing raw CSV, no reruns")
    args = ap.parse_args()

    ensure_dirs()

    if args.rebuild_summary:
        df = pd.read_csv(RESULTS / args.out)
        print(f"rebuilt {write_summary(df, args.out)} from {args.out} ({len(df)} rows)")
        return 0

    targets = args.domain or DOMAINS

    all_rows, sanity_done = [], False
    for domain in targets:
        if not input_dir(domain).exists():
            print(f"{domain}: no data - run 'python -m domain_study.datasets --all' first")
            continue
        print(f"\n{domain}")
        t0 = time.perf_counter()
        count = 0
        for name, img, ref in _load_pairs(domain, args.limit):
            all_rows.extend(run_image(domain, name, img, ref, sanity_done))
            sanity_done = True
            count += 1
            print(f"  [{count:3d}] {name} {img.shape[1]}x{img.shape[0]}", flush=True)
        print(f"  {count} images in {time.perf_counter() - t0:.1f}s")

    if not all_rows:
        print("nothing to do")
        return 1

    df = pd.DataFrame(all_rows)
    # Stable ordering makes reruns byte-identical, which is what the
    # determinism check in the plan actually tests.
    df = df.sort_values(["domain", "image", "method"], kind="stable").reset_index(drop=True)
    raw_path = RESULTS / args.out
    df.to_csv(raw_path, index=False, float_format="%.6f")

    summary_path = write_summary(df, args.out)

    n_failed = int((df["status"] == "failed").sum())
    print(f"\nwrote {raw_path} ({len(df)} rows, {n_failed} failed)")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
