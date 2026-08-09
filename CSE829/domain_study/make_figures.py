"""
Render the qualitative half of the study.

The metrics in ``summary.csv`` are global statistics, and the whole point of
CLALHE_block_artifact_notes.txt is that global statistics miss defects you can
see instantly. So every domain also gets pictures.

Two kinds of output, both written under ``results/figures``:

* **comparison tiles** - one JPEG per (domain, image, method), laid out as a
  grid by the report. Tiles rather than one composited sheet, so the labels can
  be HTML text that follows the reader's colour theme instead of pixels burned
  into the image.
* **seam close-ups** - a crop centred on the ONS grid intersection for the two
  CLALHE variants, which is where the concatenation artifact lives.

A ``manifest.json`` records what was produced so the report never guesses.

    venv/bin/python -m domain_study.make_figures
"""

import argparse
import json
import sys

import cv2
import numpy as np

from .methods import METHODS
from .paths import DOMAINS, FIGURES, ensure_dirs, input_dir, reference_dir

TILE_WIDTH = 440           # px; the long edge the report lays out at
JPEG_Q = 82
N_SHOWN = 3                # representative images per domain
CROP = 256                 # seam close-up size, in source pixels


def _resize(img, width=TILE_WIDTH):
    h, w = img.shape[:2]
    if w == width:
        return img
    return cv2.resize(img, (width, max(1, round(h * width / w))),
                      interpolation=cv2.INTER_AREA if w > width else cv2.INTER_CUBIC)


def _save(path, img, width=TILE_WIDTH):
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), _resize(img, width), [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
    return path


def _pick(files, k=N_SHOWN):
    """Evenly spaced picks from the sorted list - deterministic across runs."""
    if len(files) <= k:
        return files
    idx = np.linspace(0, len(files) - 1, k).round().astype(int)
    return [files[i] for i in dict.fromkeys(idx)]


def _seam_crop(img, sub_h, sub_w, rows, cols):
    """
    Crop centred on the first interior grid intersection.

    That corner is where two independently equalised subimages meet on both
    axes, so it is the single most informative place to look for the artifact.
    """
    h, w = img.shape[:2]
    cy = sub_h if rows > 1 else h // 2
    cx = sub_w if cols > 1 else w // 2
    half = CROP // 2
    y0 = int(np.clip(cy - half, 0, max(0, h - CROP)))
    x0 = int(np.clip(cx - half, 0, max(0, w - CROP)))
    return img[y0:y0 + CROP, x0:x0 + CROP]


def build_domain(domain):
    files = sorted(input_dir(domain).glob("*.png"))
    if not files:
        print(f"{domain}: no data - skipping")
        return {}

    entries = []
    for path in _pick(files):
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            continue
        stem = path.stem
        entry = {"image": stem, "size": [img.shape[1], img.shape[0]], "tiles": {}}

        grid = None
        for method_name, fn in METHODS:
            out, telem = fn(img)
            rel = f"{domain}/{stem}__{method_name}.jpg"
            _save(FIGURES / rel, out)
            entry["tiles"][method_name] = rel
            if method_name == "CLALHE-paper" and telem:
                grid = telem
                entry["params"] = {k: telem[k] for k in
                                   ("n_peaks", "n_valleys", "cbd", "i_cl", "ons",
                                    "grid_rows", "grid_cols")}
            # The close-up is only meaningful for the two subdivided variants,
            # plus the input as the "what was actually there" control.
            if grid and method_name in ("CLALHE-paper", "CLALHE-blended"):
                crop = _seam_crop(out, grid["sub_h"], grid["sub_w"],
                                  grid["grid_rows"], grid["grid_cols"])
                rel = f"{domain}/{stem}__{method_name}__seam.jpg"
                _save(FIGURES / rel, crop, width=CROP)
                entry.setdefault("seam_tiles", {})[method_name] = rel

        if grid:
            crop = _seam_crop(img, grid["sub_h"], grid["sub_w"],
                              grid["grid_rows"], grid["grid_cols"])
            rel = f"{domain}/{stem}__original__seam.jpg"
            _save(FIGURES / rel, crop, width=CROP)
            entry.setdefault("seam_tiles", {})["original"] = rel

        ref = reference_dir(domain) / path.name
        if ref.exists():
            ref_img = cv2.imread(str(ref), cv2.IMREAD_COLOR)
            if ref_img is not None:
                rel = f"{domain}/{stem}__reference.jpg"
                _save(FIGURES / rel, ref_img)
                entry["tiles"]["reference"] = rel

        entries.append(entry)
        print(f"  {domain}/{stem}")

    return {"images": entries, "n_total": len(files)}


def main():
    ap = argparse.ArgumentParser(description="Render comparison figures")
    ap.add_argument("--domain", choices=DOMAINS, action="append")
    args = ap.parse_args()

    ensure_dirs()
    manifest = {}
    for domain in (args.domain or DOMAINS):
        print(domain)
        built = build_domain(domain)
        if built:
            manifest[domain] = built

    out = FIGURES / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    n_tiles = sum(len(list((FIGURES / d).glob("*.jpg"))) for d in manifest)
    print(f"\n{n_tiles} tiles, manifest at {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
