# Lab 07 — Adaptive Maintenance of a Legacy System

Resurrecting [siemens/codeface](https://github.com/siemens/codeface) — archived in 2022,
written for Ubuntu 14.04 / Python 2.7 / R 3.x / MySQL 5.5 — on a modern host, and running
a full seven-range analysis of [pallets/flask](https://github.com/pallets/flask) with it.

**Start with the report: [REPORT.md](REPORT.md)** (also available as
[1422_REPORT.pdf](1422_REPORT.pdf)). Section 8 has the complete reproduction
steps; the only host requirement is Docker.

## Quick start

```bash
git clone https://github.com/siemens/codeface.git            # upstream @ e6640c93
git -C codeface apply ../patches/lab07-modernisation.patch   # this lab's fixes
mkdir -p work/git-repos work/res
git -C work/git-repos clone https://github.com/pallets/flask.git

./docker/up.sh                                                # build image + bootstrap services
docker exec -e JOBS=4 codeface \
    bash /scripts/run_analysis.sh conf/flask.conf             # run the analysis
docker exec codeface bash /scripts/collect_evidence.sh flask  # database evidence

docker exec -d codeface bash /scripts/serve_frontend.sh       # → localhost:8081/apps/projects/
```

## What is in this repository

| Path | Purpose |
|---|---|
| [REPORT.md](REPORT.md) | the lab report — outcome, strategy, chronology, evidence |
| [patches/lab07-modernisation.patch](patches/lab07-modernisation.patch) | every change on top of upstream codeface `e6640c93` |
| [docker/](docker/) | the pinned legacy runtime (Dockerfile) and all service/analysis scripts |
| [logs/](logs/) | build logs, test-suite output and run transcripts backing the report |
| [Notes.txt](Notes.txt) | condensed list of every failure and its fix |
| [1422_AI_USAGE.md](1422_AI_USAGE.md) | AI usage disclosure |

`codeface/` (the patched checkout) and `work/` (cloned target repo + generated
results) are intentionally not committed — the quick start above recreates both.
