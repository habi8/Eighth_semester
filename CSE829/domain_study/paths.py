"""Shared filesystem layout for the CLALHE domain study."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # .../CSE829
DATA = ROOT / "data"
CACHE = DATA / "_cache"                          # downloaded archives, never cleaned
RESULTS = ROOT / "results"
FIGURES = RESULTS / "figures"
PUBLIC = ROOT / "public"                         # pre-existing natural photos

# Domain folder layout:
#   data/<domain>/input/<name>.png       always present
#   data/<domain>/reference/<name>.png   only for domains with ground-truth pairs
DOMAINS = ["xray", "fundus", "underwater", "lowlight", "natural"]

DOMAIN_LABELS = {
    "xray": "Medical - chest X-ray",
    "fundus": "Medical - retinal fundus (DIARETDB1)",
    "underwater": "Underwater (UIEB)",
    "lowlight": "Low-light (LOLv1 eval15)",
    "natural": "Natural photos (control)",
}


def input_dir(domain):
    return DATA / domain / "input"


def reference_dir(domain):
    return DATA / domain / "reference"


def ensure_dirs():
    for d in (DATA, CACHE, RESULTS, FIGURES):
        d.mkdir(parents=True, exist_ok=True)
