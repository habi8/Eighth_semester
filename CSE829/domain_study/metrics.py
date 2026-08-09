"""
Image-quality metrics for the CLALHE domain study.

Three groups:

1. The paper's six (Mohammed & Isa, IEEE Access 2025) - PSNR, discrete entropy,
   AMBE, SSI, CII, RMSE - all computed between the *input* and the enhanced
   output. These reward a method for leaving the image alone, which is exactly
   why groups 2 and 3 exist.

2. Reference-based metrics, for the two domains that ship ground truth
   (UIEB, LOLv1). Scoring well here means the output actually moved toward a
   good image rather than merely staying near the bad one.

3. Domain diagnostics - noise amplification in flat dark regions, clipping,
   subimage seam strength, colourfulness. These catch the failure modes the
   global statistics in group 1 are blind to.

Everything takes numpy arrays and returns plain floats.
"""

import cv2
import numpy as np
from skimage.metrics import structural_similarity

EPS = 1e-8


def to_gray(img):
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ─────────────────────────────────────────────
#  1. the paper's six
# ─────────────────────────────────────────────

def mse(a, b):
    return float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))


def psnr(original, enhanced):
    """Eq. (10). Capped at 100 dB for identical images."""
    m = mse(original, enhanced)
    if m < 1e-10:
        return 100.0
    return float(10.0 * np.log10((255.0 ** 2) / m))


def rmse(original, enhanced):
    return float(np.sqrt(mse(original, enhanced)))


def entropy(img):
    """Eq. (7): discrete entropy of the 256-bin grey histogram, in bits."""
    hist = cv2.calcHist([to_gray(img)], [0], None, [256], [0, 256]).flatten()
    p = hist / max(hist.sum(), EPS)
    p = p[p > 0]
    return float(-np.sum(p * np.log2(p)))


def ambe(original, enhanced):
    """Eq. (8): absolute mean brightness error."""
    return float(abs(np.mean(original.astype(np.float64)) -
                     np.mean(enhanced.astype(np.float64))))


def ssi(original, enhanced):
    """Eq. (17): structural similarity between input and output."""
    return float(structural_similarity(to_gray(original), to_gray(enhanced),
                                       data_range=255))


def frame_mask(img, thresh=2):
    """
    The dead black frame around the picture, if there is one.

    A retinal fundus photograph is a circle on a black square - 13.5% of every
    DIARETDB image is exactly zero - and several X-ray exports are letterboxed.
    That frame is not image content, and it wrecks any contrast statistic that
    divides by intensity: with b close to 0, Michelson contrast pins at 1, so
    the frame edge drowns out the anatomy, and merely lifting the frame off
    zero looks like a catastrophic loss of contrast.

    Detected as the near-black connected components that touch the image
    border, so an ordinary dark object inside the scene is never removed.
    """
    g = to_gray(img)
    dark = (g <= thresh).astype(np.uint8)
    if dark.sum() == 0:
        return np.zeros(g.shape, dtype=bool)
    n, labels = cv2.connectedComponents(dark, connectivity=4)
    border = np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
    ids = [i for i in np.unique(border) if i != 0]
    if not ids:
        return np.zeros(g.shape, dtype=bool)
    return np.isin(labels, ids)


def _valid_blocks(content, block):
    """Block centres whose block is at least 90% image content."""
    frac = cv2.boxFilter(content.astype(np.float64), -1, (block, block), normalize=True)
    half = block // 2
    return frac[half::block, half::block] >= 0.9


def _block_michelson(gray, keep, block=32):
    """
    Mean Michelson contrast C = |f - b| / (f + b) over non-overlapping blocks.

    Eq. (12) defines f as the mean grey level of a chosen ROI and b as the mean
    of the surrounding area. The paper picks that ROI by hand. With no ROI
    annotations across five domains we evaluate it densely instead: every
    block is an ROI, its surround is the ring of the 3x3 block neighbourhood
    around it, and the per-image contrast is the average over blocks that are
    real image content. This is a documented deviation from the paper, applied
    identically to every arm so the ratio in ``cii`` stays a fair comparison.
    """
    g = gray.astype(np.float64)
    f = cv2.boxFilter(g, -1, (block, block), normalize=True)
    outer = cv2.boxFilter(g, -1, (3 * block, 3 * block), normalize=True)
    b = (9.0 * outer - f) / 8.0                    # ring mean, block removed
    c = np.abs(f - b) / (f + b + EPS)
    half = block // 2
    c = c[half::block, half::block]                # block centres only
    return float(np.mean(c[keep])) if keep.any() else float("nan")


def cii(original, enhanced, block=32):
    """
    Eq. (11): contrast improvement index, >1 means contrast went up.

    The block selection is computed from the original and reused for the
    enhanced image, so both sides of the ratio are measured over the same
    pixels no matter what the method did to the frame.
    """
    keep = _valid_blocks(~frame_mask(original), block)
    c_orig = _block_michelson(to_gray(original), keep, block)
    c_enh = _block_michelson(to_gray(enhanced), keep, block)
    return float(c_enh / (c_orig + EPS))


# ─────────────────────────────────────────────
#  2. reference-based
# ─────────────────────────────────────────────

def psnr_ref(enhanced, reference):
    """PSNR against ground truth - the yardstick the paper's PSNR is not."""
    if enhanced.shape != reference.shape:
        reference = cv2.resize(reference, (enhanced.shape[1], enhanced.shape[0]))
    return psnr(reference, enhanced)


def ssim_ref(enhanced, reference):
    if enhanced.shape != reference.shape:
        reference = cv2.resize(reference, (enhanced.shape[1], enhanced.shape[0]))
    return ssi(reference, enhanced)


# ─────────────────────────────────────────────
#  3. domain diagnostics
# ─────────────────────────────────────────────

def flat_dark_mask(original, intensity_pct=25, flatness_pct=25, win=7):
    """
    Pixels that are dark, locally flat, and actual image content.

    On a chest X-ray this is the low-density soft tissue and the air field
    inside the detector; on a low-light photo it is the crushed shadow region.
    Whatever a method does to the texture here is mostly noise amplification,
    because there was little signal to begin with. The mask comes from the
    original alone, so every arm is judged on the same pixels.

    The dead frame is excluded (see ``frame_mask``): a region that is exactly
    zero everywhere has no noise to amplify, and including it only produces a
    0/0 ratio.
    """
    g = to_gray(original).astype(np.float64)
    mean = cv2.boxFilter(g, -1, (win, win), normalize=True)
    local_var = cv2.boxFilter(g * g, -1, (win, win), normalize=True) - mean ** 2
    local_std = np.sqrt(np.maximum(local_var, 0.0))

    content = ~frame_mask(original)
    if content.sum() < 100:
        return np.zeros(g.shape, dtype=bool)

    dark = g <= np.percentile(g[content], intensity_pct)
    flat = local_std <= np.percentile(local_std[content], flatness_pct)
    return dark & flat & content


def bg_std(img, mask):
    """Absolute pixel std inside the flat dark region, in grey levels."""
    if mask is None or mask.sum() < 100:
        return float("nan")
    return float(to_gray(img).astype(np.float64)[mask].std())


def bg_noise_gain(original, enhanced, mask=None):
    """
    How much louder the flat dark region got: std(enhanced)/std(original).

    1.0 means untouched; large values mean the method spent its dynamic range
    amplifying fluctuation in a region that carries little information.

    Returns NaN when the region is too quiet in the input to support a ratio
    (under half a grey level of variation), because dividing one near-zero by
    another produces a number with no meaning. Read ``bg_std`` in that case.
    """
    if mask is None:
        mask = flat_dark_mask(original)
    if mask.sum() < 100:
        return float("nan")
    o = bg_std(original, mask)
    if not np.isfinite(o) or o < 0.5:
        return float("nan")
    return float(bg_std(enhanced, mask) / o)


def clip_fraction(img):
    """Percent of pixels pinned at 0 or 255 - blown highlights, crushed shadows."""
    g = to_gray(img)
    return float(100.0 * np.mean((g == 0) | (g == 255)))


def seam_strength(img, sub_h, sub_w, rows, cols, guard=2):
    """
    How visible the subimage grid is, as a ratio.

    Along every interior boundary of the ONS grid we take the mean absolute
    step across the boundary, and divide by the mean absolute step over all
    other lines in the image. A value near 1 means the boundaries look like
    ordinary image content; a value well above 1 means the grid itself is
    visible - the block artifact described in CLALHE_block_artifact_notes.txt.

    Returns NaN when the grid has no interior boundary to measure.
    """
    g = to_gray(img).astype(np.float64)
    h, w = g.shape
    ratios = []

    if rows > 1 and sub_h > guard:
        dy = np.abs(np.diff(g, axis=0)).mean(axis=1)          # step at each row
        lines = [r * sub_h for r in range(1, rows) if 0 < r * sub_h < h]
        if lines:
            on = np.array([dy[y - 1] for y in lines])
            off_mask = np.ones(len(dy), dtype=bool)
            for y in lines:
                off_mask[max(0, y - 1 - guard):min(len(dy), y + guard)] = False
            if off_mask.sum() > 0:
                ratios.append(on.mean() / (dy[off_mask].mean() + EPS))

    if cols > 1 and sub_w > guard:
        dx = np.abs(np.diff(g, axis=1)).mean(axis=0)
        lines = [c * sub_w for c in range(1, cols) if 0 < c * sub_w < w]
        if lines:
            on = np.array([dx[x - 1] for x in lines])
            off_mask = np.ones(len(dx), dtype=bool)
            for x in lines:
                off_mask[max(0, x - 1 - guard):min(len(dx), x + guard)] = False
            if off_mask.sum() > 0:
                ratios.append(on.mean() / (dx[off_mask].mean() + EPS))

    return float(np.mean(ratios)) if ratios else float("nan")


def colorfulness(img):
    """Hasler & Suesstrunk colourfulness - does the underwater cast survive?"""
    if img.ndim == 2:
        return 0.0
    b, g, r = (c.astype(np.float64) for c in cv2.split(img))
    rg = r - g
    yb = 0.5 * (r + g) - b
    std = np.sqrt(rg.std() ** 2 + yb.std() ** 2)
    mean = np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)
    return float(std + 0.3 * mean)
