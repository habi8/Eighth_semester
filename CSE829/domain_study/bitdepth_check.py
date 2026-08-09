"""
Does CLALHE survive the bit depth medical imaging actually uses?

Every source in this study is 8-bit, because that is what is publicly
downloadable. Native medical data is not: DICOM CT and CR/DR radiographs are
stored at 12 or 16 bits per pixel, and the whole point of contrast enhancement
there is to make use of that extra range.

Two places in CLALHE assume 8 bits:

  * ``part1_determine_optimal_params`` calls
    ``cv2.calcHist([img], [0], None, [256], [0, 256])`` - for a 16-bit image
    every pixel above 255 falls outside the range and is dropped, so the peak
    and valley counts that drive CBD, I_CL and ONS are computed from whatever
    slice of the image happens to be dark.
  * ``_compute_psnr`` hardcodes ``255.0`` as the peak signal, so the CIQI
    fitness used to select I_CL is on the wrong scale.

This probe takes one real X-ray, builds a 16-bit version carrying the same
picture, and shows what each stage reports. It is a demonstration, not a fix.

    venv/bin/python -m domain_study.bitdepth_check
"""

import sys

import cv2
import numpy as np

from .methods import ClalhePaper
from .paths import input_dir


def main():
    files = sorted(input_dir("xray").glob("*.png"))
    if not files:
        print("no X-ray data - run 'python -m domain_study.datasets --domain xray'")
        return 1

    bgr = cv2.imread(str(files[0]), cv2.IMREAD_COLOR)
    gray8 = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Same picture, 16-bit container: exactly what a DICOM CR image looks like.
    gray16 = (gray8.astype(np.uint16) * 257)

    print(f"image: {files[0].name}  {gray8.shape[1]}x{gray8.shape[0]}")
    print(f"  8-bit  range {gray8.min():5d} .. {gray8.max():5d}")
    print(f"  16-bit range {gray16.min():5d} .. {gray16.max():5d}")

    print("\nhistogram coverage with the hardcoded [0, 256] range:")
    for label, img in (("8-bit", gray8), ("16-bit", gray16)):
        hist = cv2.calcHist([img], [0], None, [256], [0, 256]).flatten()
        counted = hist.sum()
        total = img.size
        print(f"  {label:6s} {counted:12.0f} of {total} pixels "
              f"({100 * counted / total:5.1f}% of the image is in the histogram)")

    print("\nparameters CLALHE derives from that histogram:")
    header = f"  {'input':8s} {'n_peaks':>8s} {'n_valleys':>10s} {'CBD':>5s} {'I_CL':>8s} {'ONS':>5s}"
    print(header)
    for label, img in (("8-bit", gray8), ("16-bit", gray16)):
        obj = ClalhePaper()
        try:
            obj.part1_determine_optimal_params(img)
            ons = max(2, int(np.ceil(np.log2(max(obj.n_valleys, 2)))))
            if ons % 2:
                ons += 1
            print(f"  {label:8s} {obj.n_peaks:8d} {obj.n_valleys:10d} "
                  f"{obj.optimal_cbd:5d} {obj.optimal_i_cl:8.4f} {ons:5d}")
        except Exception as e:
            print(f"  {label:8s} raised {type(e).__name__}: {e}")

    print("\nfull pipeline on the 16-bit image:")
    try:
        out = ClalhePaper().enhance(gray16)
        print(f"  returned dtype={out.dtype} range {out.min()} .. {out.max()}")
        if out.dtype == np.uint16 and out.max() <= 255:
            print("  -> output collapsed into the bottom 0.4% of the 16-bit range")
    except Exception as e:
        print(f"  raised {type(e).__name__}: {e}")

    print("\nVerdict: CLALHE does not reject 16-bit input, it silently derives its\n"
          "parameters from a truncated histogram. Native DICOM must be windowed to\n"
          "8 bits before use, which is itself a contrast decision made outside the\n"
          "method - and the paper never states this constraint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
