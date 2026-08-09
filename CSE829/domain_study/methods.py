"""
The five enhancement arms compared in the domain study.

Every arm takes and returns an 8-bit BGR image, and every arm touches only the
LAB L-channel - the same colour handling the two CLALHE implementations already
use in their own ``enhance()``. That keeps chrominance identical across arms so
any measured difference is attributable to the luminance algorithm alone.

Arms that expose internal parameters return them through ``telemetry``; the
driver logs those to answer the "does CLALHE actually adapt?" question.
"""

import importlib
import sys
from pathlib import Path

import cv2
import numpy as np

# CLALHE.py and CLALHE_new.py live one level up and both define a class called
# CLALHE. The module names differ, so plain imports are unambiguous.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ClalheBlended = importlib.import_module("CLALHE").CLALHE
ClalhePaper = importlib.import_module("CLALHE_new").CLALHE


def _on_luminance(image, fn):
    """Run ``fn`` on the L-channel of LAB and rebuild the BGR image."""
    if image.ndim == 2:
        return fn(image)
    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = fn(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


# ─────────────────────────────────────────────
#  arms
# ─────────────────────────────────────────────

def m_original(image):
    """Identity. The sanity anchor: PSNR 100, SSI 1.0, CII 1.0, AMBE 0."""
    return image.copy(), {}


def m_he(image):
    """Global histogram equalisation - the classic over-enhancement baseline."""
    return _on_luminance(image, cv2.equalizeHist), {}


def m_clahe(image):
    """Stock OpenCV CLAHE at its documented defaults."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return _on_luminance(image, clahe.apply), {"cbd": 8, "i_cl": 2.0}


def _clalhe_telemetry(obj, shape, ceil_grid):
    """
    Pull the parameters CLALHE derived for this image, plus the ONS grid.

    ``ceil_grid`` mirrors the difference between the two implementations:
    CLALHE_new.part2_enhance walks ``ceil(h/sub_h)`` rows, CLALHE.part2_enhance
    walks ``h // sub_h``. The logged grid must be the grid that actually ran.
    """
    h, w = shape[:2]
    n_valleys = getattr(obj, "n_valleys", 0)
    # Reproduce Eq. (5)/(6) exactly as part2_enhance does, so the logged grid is
    # the grid that actually ran.
    if n_valleys <= 1:
        ons = 2
    else:
        ons = int(np.ceil(np.log2(n_valleys)))
        if ons % 2 != 0:
            ons += 1
        ons = max(ons, 2)
    if ons == 2:
        sub_h, sub_w = h, w // 2
    else:
        sub_h, sub_w = h // 2, w // (ons // 2)
    sub_h, sub_w = max(sub_h, 1), max(sub_w, 1)
    if ceil_grid:
        rows, cols = int(np.ceil(h / sub_h)), int(np.ceil(w / sub_w))
    else:
        rows, cols = h // sub_h, w // sub_w
    return {
        "n_peaks": getattr(obj, "n_peaks", np.nan),
        "n_valleys": n_valleys,
        "cbd": obj.optimal_cbd,
        "i_cl": obj.optimal_i_cl,
        "ons": ons,
        "grid_rows": max(1, rows),
        "grid_cols": max(1, cols),
        "sub_h": sub_h,
        "sub_w": sub_w,
    }


def m_clalhe_paper(image):
    """CLALHE as published: subimages concatenated with hard edges."""
    obj = ClalhePaper()                    # per-image state - never reuse
    out = obj.enhance(image)
    return out, _clalhe_telemetry(obj, image.shape, ceil_grid=True)


def m_clalhe_blended(image):
    """CLALHE with the cross-fade fix from CLALHE.py."""
    obj = ClalheBlended()
    out = obj.enhance(image)
    # CLALHE.py stores peak/valley counts only as return values, so recover the
    # counts the same way part1 does before reading the rest of the telemetry.
    hist = cv2.calcHist([_lchannel(image)], [0], None, [256], [0, 256]).flatten()
    peaks, _, valleys, _ = obj._find_peaks_valleys(hist)
    obj.n_peaks, obj.n_valleys = len(peaks), len(valleys)
    return out, _clalhe_telemetry(obj, image.shape, ceil_grid=False)


def _lchannel(image):
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2LAB)[:, :, 0].copy()


# Order matters: it is the column order in every table and figure.
METHODS = [
    ("original", m_original),
    ("HE", m_he),
    ("CLAHE", m_clahe),
    ("CLALHE-paper", m_clalhe_paper),
    ("CLALHE-blended", m_clalhe_blended),
]

METHOD_NAMES = [name for name, _ in METHODS]
