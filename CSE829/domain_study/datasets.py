"""
Fetch and normalise the test images for the CLALHE domain study.

Every domain ends up in the same shape on disk::

    data/<domain>/input/<name>.png        the image fed to the enhancement methods
    data/<domain>/reference/<name>.png    ground truth, only where one exists

so the rest of the study never needs to know where an image came from.

All sources are public and non-gated: no Kaggle key, no Google Drive.
Archives are cached under ``data/_cache`` and never re-downloaded.

Drop-in convention: if ``data/<domain>/input`` already contains images, that
domain is left completely alone. To use your own data for a domain, put the
files there before running this module.
"""

import argparse
import io
import json
import random
import shutil
import sys
import urllib.request
import zipfile

import cv2
import numpy as np

from .paths import DATA, CACHE, PUBLIC, DOMAINS, input_dir, reference_dir, ensure_dirs

SEED = 829  # fixed so the sampled subset is identical on every machine

HF = "https://huggingface.co/datasets"
ARCHIVES = {
    "cxr_test.zip": f"{HF}/trpakov/chest-xray-classification/resolve/main/data/test.zip",
    "lolv1_test.zip": f"{HF}/okita-souji/LOLv1/resolve/main/test.zip",
    # Note: this repository is *named* DIARETDB1 but the archive it serves is
    # DIARETDB0 v1.1 - the sibling database from the same Kuopio group, same
    # fundus camera and 50 deg FOV, 130 images at 1500x1152. The paper used
    # DIARETDB1 (130 images at 1500x1100). The official LUT mirror for
    # DIARETDB1 is dead, so this is the closest reachable stand-in and the
    # report must describe it as such.
    "diaretdb0.zip": f"{HF}/MahsaTorki/DIARETDB1_Database/resolve/main/DIARETDB1.zip",
}

N_PER_DOMAIN = {"xray": 40, "fundus": 40, "underwater": 40, "lowlight": 15, "natural": 99}


# ─────────────────────────────────────────────
#  helpers
# ─────────────────────────────────────────────

def _download(name, url):
    """Fetch an archive into the cache, skipping if it is already there."""
    dest = CACHE / name
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  cached  {name} ({dest.stat().st_size / 1e6:.0f} MB)")
        return dest
    print(f"  fetching {name} ...", flush=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.rename(dest)
    print(f"  saved   {name} ({dest.stat().st_size / 1e6:.0f} MB)")
    return dest


def _already_populated(domain):
    d = input_dir(domain)
    return d.exists() and any(d.glob("*.png"))


def _prepare(domain):
    """Create (and clear) the output folders for a domain."""
    for d in (input_dir(domain), reference_dir(domain)):
        if d.exists():
            shutil.rmtree(d)
    input_dir(domain).mkdir(parents=True, exist_ok=True)
    return input_dir(domain)


def _write(path, img):
    """Write an image as 8-bit BGR PNG, normalising away odd input formats."""
    if img is None:
        return False
    if img.dtype != np.uint8:                       # 16-bit sources -> 8-bit
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return cv2.imwrite(str(path), img)


def _decode(raw):
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def _sample(items, n):
    """Deterministic subset: sorted first, then a seeded shuffle."""
    items = sorted(items)
    if len(items) <= n:
        return items
    rng = random.Random(SEED)
    return sorted(rng.sample(items, n))


# ─────────────────────────────────────────────
#  per-domain fetchers
# ─────────────────────────────────────────────

def fetch_xray(n):
    """Chest X-ray: Kermany pneumonia set, Roboflow-exported 640x640 JPEGs."""
    zpath = _download("cxr_test.zip", ARCHIVES["cxr_test.zip"])
    out = _prepare("xray")
    with zipfile.ZipFile(zpath) as z:
        names = [x for x in z.namelist() if x.lower().endswith((".jpg", ".png"))]
        # keep both classes so the domain is not all-pathological
        normal = _sample([x for x in names if x.startswith("NORMAL/")], n // 2)
        pneumo = _sample([x for x in names if x.startswith("PNEUMONIA/")], n - len(normal))
        for i, name in enumerate(normal + pneumo):
            cls = name.split("/")[0].lower()
            _write(out / f"{cls}_{i:03d}.png", _decode(z.read(name)))
    return len(list(out.glob("*.png"))), 0


def fetch_fundus(n):
    """Retinal fundus: DIARETDB0 v1.1, 1500x1152 (see ARCHIVES note)."""
    zpath = _download("diaretdb0.zip", ARCHIVES["diaretdb0.zip"])
    out = _prepare("fundus")
    with zipfile.ZipFile(zpath) as z:
        # only the fundus photographs - the archive also ships binary masks
        # and expert groundtruth overlays, which are not photographs
        names = [x for x in z.namelist()
                 if "diaretdb0_fundus_images/" in x and x.lower().endswith(".png")]
        for i, name in enumerate(_sample(names, n)):
            _write(out / f"fundus_{i:03d}.png", _decode(z.read(name)))
    return len(list(out.glob("*.png"))), 0


def fetch_lowlight(n):
    """Low-light: LOLv1 eval15 - paired low / normal-light captures."""
    zpath = _download("lolv1_test.zip", ARCHIVES["lolv1_test.zip"])
    out = _prepare("lowlight")
    ref = reference_dir("lowlight")
    ref.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath) as z:
        lows = [x for x in z.namelist() if x.startswith("test/low/") and x.endswith(".png")]
        for i, low in enumerate(_sample(lows, n)):
            high = low.replace("test/low/", "test/high/")
            if high not in z.namelist():
                continue
            _write(out / f"lol_{i:03d}.png", _decode(z.read(low)))
            _write(ref / f"lol_{i:03d}.png", _decode(z.read(high)))
    return len(list(out.glob("*.png"))), len(list(ref.glob("*.png")))


def fetch_underwater(n):
    """
    Underwater: UIEB val split, via the HF datasets-server rows API.

    The parquet shards are ~400 MB each; the rows API hands back per-image
    URLs instead, so we download only the images we actually use.
    """
    out = _prepare("underwater")
    ref = reference_dir("underwater")
    ref.mkdir(parents=True, exist_ok=True)

    url = ("https://datasets-server.huggingface.co/rows"
           "?dataset=Hikari0608%2FUIEB&config=default&split=val&offset=0&length=100")
    with urllib.request.urlopen(url, timeout=120) as r:
        rows = json.load(r)["rows"]

    picked = _sample(list(range(len(rows))), n)
    for i, idx in enumerate(picked):
        row = rows[idx]["row"]
        try:
            with urllib.request.urlopen(row["raw"]["src"], timeout=120) as r:
                raw = _decode(r.read())
            with urllib.request.urlopen(row["gt"]["src"], timeout=120) as r:
                gt = _decode(r.read())
        except Exception as e:                       # a single flaky asset URL
            print(f"    skip row {idx}: {e}")
            continue
        _write(out / f"uw_{i:03d}.png", raw)
        _write(ref / f"uw_{i:03d}.png", gt)
    return len(list(out.glob("*.png"))), len(list(ref.glob("*.png")))


def fetch_natural(n):
    """Control domain: the photographs already sitting in CSE829/public."""
    out = _prepare("natural")
    names = [p for p in PUBLIC.iterdir()
             if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    for i, p in enumerate(sorted(names)[:n]):
        _write(out / f"{p.stem}.png", cv2.imread(str(p), cv2.IMREAD_COLOR))
    return len(list(out.glob("*.png"))), 0


FETCHERS = {
    "xray": fetch_xray,
    "fundus": fetch_fundus,
    "underwater": fetch_underwater,
    "lowlight": fetch_lowlight,
    "natural": fetch_natural,
}


def fetch(domain, force=False):
    if _already_populated(domain) and not force:
        n = len(list(input_dir(domain).glob("*.png")))
        print(f"{domain:11s} already populated ({n} images) - skipping")
        return n, len(list(reference_dir(domain).glob("*.png"))) if reference_dir(domain).exists() else 0
    print(f"{domain:11s} preparing ...")
    n_in, n_ref = FETCHERS[domain](N_PER_DOMAIN[domain])
    print(f"{domain:11s} ready: {n_in} inputs" + (f", {n_ref} references" if n_ref else ""))
    return n_in, n_ref


def main():
    ap = argparse.ArgumentParser(description="Fetch domain-study test images")
    ap.add_argument("--all", action="store_true", help="fetch every domain")
    ap.add_argument("--domain", choices=DOMAINS, help="fetch a single domain")
    ap.add_argument("--force", action="store_true", help="re-fetch even if populated")
    args = ap.parse_args()

    ensure_dirs()
    targets = DOMAINS if args.all or not args.domain else [args.domain]

    total = 0
    for d in targets:
        total += fetch(d, force=args.force)[0]
    print(f"\n{total} images across {len(targets)} domains, under {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
