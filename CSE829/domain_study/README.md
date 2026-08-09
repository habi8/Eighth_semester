# CLALHE domain generalization study

Does CLALHE (Mohammed & Isa, IEEE Access 2025) work outside the images it was
published on? The paper evaluated three datasets — Faces 1999, Pasadena-Houses
2000 and DIARETDB1 — two of which are ordinary consumer photographs. This
package re-runs the method over five domains it was never tested on and scores
it against ground truth wherever ground truth exists.

## Running it

```bash
venv/bin/python -m domain_study.datasets --all      # ~350 MB, 5 domains, public sources
venv/bin/python -m domain_study.run_study           # results/raw_results.csv + summary.csv
venv/bin/python -m domain_study.make_figures        # results/figures/*.jpg + manifest.json
venv/bin/python -m domain_study.report              # domain_study/report.html
venv/bin/python -m domain_study.bitdepth_check      # the 16-bit probe
```

Reruns are byte-identical apart from `runtime_s`. `run_study.py --rebuild-summary`
recomputes `summary.csv` from an existing raw CSV without re-running anything.

## What is where

| File | Role |
|---|---|
| `paths.py` | filesystem layout and domain names |
| `datasets.py` | fetches and normalises the five domains into `data/<domain>/input` |
| `methods.py` | the five arms: input, HE, CLAHE, CLALHE-paper, CLALHE-blended |
| `metrics.py` | the paper's six metrics, reference-based metrics, domain diagnostics |
| `run_study.py` | the driver; writes the two CSVs |
| `make_figures.py` | comparison tiles and seam close-ups |
| `report.py` | generates `report.html` from the CSVs — no numbers are hand-typed |
| `bitdepth_check.py` | shows what happens to 16-bit (DICOM-scale) input |

The two CLALHE implementations under test live one level up:
`CLALHE_new.py` (paper-faithful, hard concatenation) and `CLALHE.py` (same
algorithm with a cross-fade write-back). `data/` and `results/` are gitignored.

## Domains

| Domain | Source | n | Ground truth |
|---|---|---|---|
| Chest X-ray | HF `trpakov/chest-xray-classification` | 40 | no |
| Retinal fundus | HF `MahsaTorki/DIARETDB1_Database` — actually **DIARETDB0** | 40 | no |
| Underwater | HF `Hikari0608/UIEB`, via the datasets-server rows API | 40 | yes |
| Low-light | HF `okita-souji/LOLv1` (eval15) | 15 | yes |
| Natural photos | the existing `public/` images, as a control | 11 | no |

## Findings, in one paragraph

CLALHE generalises poorly. As published it leaves a visible subimage grid in
every domain tested — 2.8× to 4.3× more visible than the image's own content,
and on a chest radiograph it crosses the lung fields. Its adaptive clip limit
sits on its floor of 1.0 for most images in most domains, and on all 40 X-rays
it selected identical parameters, so the adaptivity claim does not hold up.
Where ground truth exists it loses: on low-light images plain global HE gains
6.5 dB against the reference where CLALHE gains 0.8, and CLALHE produces the
best result on 0 of 15 images. It never beats stock OpenCV CLAHE on any domain
here, while running 30–120× slower. On 16-bit input it silently reads 4% of the
histogram, finds zero peaks, and falls back to fixed defaults.

Full write-up with figures: `report.html`.
