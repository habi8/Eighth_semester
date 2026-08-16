# Running chronology (raw notes for the report)

## Phase 0 — Reconnaissance

**Host:** Ubuntu 24.04.2 LTS, kernel 7.0.0-28, x86_64, 15 GiB RAM, 27 GiB free.
Available: Docker 28.3.3 + Compose v2.39.1, Python 3.12.3, git 2.43.0, OpenJDK 21.
**Absent:** any Python 2, any R, any MySQL/PostgreSQL.

**Target:** `github.com/siemens/codeface`, HEAD = `e6640c93` (2019-08-22).
Archived 2022.

What the repo declares it needs (from `.travis.yml`, `Vagrantfile`,
`integration-scripts/*.sh`, `packages.r`, `setup.py`):
- Ubuntu **14.04 Trusty** or 16.04 Xenial (`install_repositories.sh` hard-aborts
  on anything else: `*) echo "Unsupported version of Ubuntu detected, aborting"`)
- **Python 2.7** + `MySQL-python`, `python-ctags`, `progressbar`, `PyYAML`, `jira`
- **R** + ~45 CRAN/Bioconductor/GitHub packages
- **MySQL 5.5** (Travis explicitly *downgrades* from 5.6 to 5.5)
- **Node.js** ID service (express 4, mysql 2.x)
- `exuberant-ctags`, `sloccount`, `graphviz`, `lualatex`

## Phase 1 — Which legacy sources still exist? (availability probe)

| Source | Result |
|---|---|
| `old-releases.ubuntu.com/ubuntu/dists/xenial` | **404** — gone |
| `archive.ubuntu.com/ubuntu/dists/bionic` | **200** — 18.04 still live |
| `cloud.r-project.org/bin/linux/ubuntu/bionic-cran35` | **200** — R up to 3.6.3 |
| `packagemanager.posit.co/cran/__linux__/bionic/<date>` | **200** — date-pinned CRAN |
| `bootstrap.pypa.io/pip/2.7/get-pip.py` | **200** |
| PyPI `MySQL-python`, `python-ctags`, `progressbar` | **200** |

=> **Decision: Ubuntu 18.04 (bionic) as the base image.** It is the newest
Ubuntu that still ships `python2.7` in main *and* still has live archives, and
CRAN still hosts an R build for it. 14.04/16.04 were rejected because their
package archives are dead — the documented Vagrant path is unbuildable today.

Bonus find: bionic ships `exuberant-ctags 1:5.9~svn20110310-11ubuntu0.1`.
`codeface/util.py:check4ctags()` asserts the version string *starts with*
`"Exuberant Ctags 5.9~svn20110310"` and raises otherwise — bionic matches
exactly. On a modern distro (universal-ctags) this check can never pass.

## Phase 2 — Python 2.7 dependency reconstruction

- Bootstrapped pip from `bootstrap.pypa.io/pip/2.7/get-pip.py`
  (pip 20.3.4 / setuptools 44.1.1 / wheel 0.37.1); bionic's own `python-pip`
  is too old to negotiate with today's PyPI.
- Pinned every dependency to its last py2.7-compatible release
  (`docker/python_requirements_pinned.txt`). Unpinned installs resolve to
  py3-only releases and fail.
- **Bug found in `setup.py`:** `install_requires` lists `'VCS'`. Codeface's
  version-control abstraction is the *in-tree* module `codeface/VCS.py`.
  `VCS` on PyPI is an unrelated 2010–2011 package
  ("Various version Control System management abstraction layer", M. Kuzminski).
  Declaring it makes pip download foreign code that is never imported.
  **Patched:** removed `'VCS'` from `install_requires`.
- `MySQL-python==1.2.5` compiled successfully against bionic's
  `libmysqlclient-dev` (MySQL 5.7 headers) — no patch needed.
- `jira` is needed even for `codeface run`: `project.py` imports
  `codeface.conway`, which imports `jira` at module scope. Pinned `jira==2.0.0`.

## Phase 3 — R dependency reconstruction (the hard part)

Upstream `packages.r` is unusable as written, for four independent reasons:
1. It calls `biocLite()` from `bioconductor.org/biocLite.R` — retired in 2019
   (Bioconductor 3.8+); the URL now only emits an error.
2. It installs from **live CRAN HEAD**, whose current versions require R >= 4.x
   and refuse to install on R 3.6.
3. It pulls 4 packages from GitHub via `devtools::install_github`
   (`tm.plugin.mail`, `snatm`, `shinyGridster`, `shinybootstrap2`) — all only
   used by the mailing-list and Shiny front-end paths, not by `codeface run`.
4. It passes `dependencies=TRUE`, i.e. resolves **Suggests** too.

**Scoping the problem:** rather than install all ~45 packages, I computed the
transitive `source()` closure of the three scripts `codeface run` actually
executes (`R/cluster/persons.r`, `R/complexity.r`, `R/analyse_ts.r`).
That reaches 23 R files requiring **33 libraries** (29 CRAN + 3 Bioconductor +
2 base). The mailing-list-only packages (`snatm`, `tm.plugin.mail`, `wordnet`)
and Shiny extras are not on this path.

**Build attempt #1 (aborted):** pinned CRAN to the PPM snapshot `2020-04-01`
and kept `dependencies=TRUE`. With Suggests resolved, the 29 roots expand to a
**1 544-package closure** — it was downloading `usethis` (a devtools
dependency) when I killed it. The `PACKAGES` index it was reading listed
source tarballs, which led me to conclude PPM no longer ships binaries for
snapshots this old. **That conclusion was wrong** and is corrected in attempt
#3 below; the index is source-only but the *downloads* are content-negotiated.

**Considered and rejected:** Michael Rutter's `ppa:marutter/c2d4u3.5` is still
alive for bionic with 6 201 prebuilt `r-cran-*` debs covering almost everything
needed. Rejected because those debs are built against **R 4.4** (e.g.
`r-cran-igraph 1.3.5`), while we run R 3.6.3 — an ABI mismatch — and R 4.x also
flips the `stringsAsFactors` default and carries a decade of igraph API drift,
which is exactly the class of silent breakage that would corrupt results from
2013-era code.

**Build attempt #3 — the `libglpk.so.40` failure.** With the restricted
dependency fields the build got much further but ended:

```
Error: package or namespace load failed for 'igraph' in dyn.load(file, DLLpath = DLLpath, ...):
 unable to load shared object '/usr/local/lib/R/site-library/igraph/libs/igraph.so':
  libglpk.so.40: cannot open shared object file: No such file or directory
Error: package 'igraph' could not be loaded
ERROR: required packages failed to install: igraph, markovchain, BiRewire
```

`markovchain` and `BiRewire` are collateral damage — both depend on `igraph`.

The log line `* installing *binary* package 'igraph'` corrected my earlier
mistake: **97 of the 101 packages were installed as prebuilt binaries**; only
the four Bioconductor ones compiled from source. PPM's `PACKAGES` index
advertises source tarballs, but the actual downloads are content-negotiated on
the R `User-Agent` and return binaries. That is why the build took 8 minutes
rather than hours.

The consequence is subtle and worth stating plainly: `install.packages()`
reported **success** for igraph. A prebuilt binary is only unpacked, never
linked, so a missing shared-library dependency is not detected at install
time — it surfaces later at `dyn.load()`. I confirmed the exact requirement by
downloading the artefact PPM actually serves and reading its ELF headers:

```
$ objdump -p igraph/libs/igraph.so | grep NEEDED
  NEEDED  libxml2.so.2      NEEDED  libgmp.so.10     NEEDED  libglpk.so.40
  NEEDED  liblapack.so.3    NEEDED  libblas.so.3     NEEDED  libgfortran.so.4
  ...
```

`libgmp.so.10` and `libglpk.so.40` were absent because I had built a
deliberately slim image, whereas PPM's build host was fuller.

**Fix:** an extra APT layer installing `libglpk-dev libgmp-dev libmpfr-dev
libicu-dev libblas-dev liblapack-dev`, placed immediately before the R package
layer so the expensive earlier layers stay cached. I also changed the R
verifier to print the actual `dyn.load` message per failing package rather
than just naming it, so the next iteration would not need this manual
forensics.

**Build attempt #2 (adopted):** keep R 3.6.3 + CRAN snapshot 2020-04-01
(deliberately dated just *before* R 4.0.0 shipped, so every resolved version
still declares R 3.x compatibility) and Bioconductor 3.10 (the release matched
to R 3.6), but restrict resolution to `c("Depends","Imports","LinkingTo")`.
Closure drops **1 544 -> 96 packages** (49 needing compilation) — same
functionality, ~16x less to build. Required and optional sets were split into
separate image layers so a best-effort extra cannot invalidate the core cache.
Result: 29 CRAN roots built from source in ~8 minutes on 12 cores.

## Phase 4 — Services and bootstrap

Replaced the three Vagrant-era provisioning scripts (`setup_database.sh`,
`install_codeface_python.sh`, `install_codeface_node.sh`) with one idempotent
`docker/bootstrap_codeface.sh`. They could not be reused as-is: each assumes a
Vagrant VM with a `vagrant` user, passwordless `sudo`, and `chown vagrant.vagrant`.

**MySQL.** 5.7.42 from bionic stands in for the required 5.5. Two adaptations:
- `sql_mode=` is emptied in `/etc/mysql/conf.d/codeface.cnf`. MySQL 5.7 enables
  `ONLY_FULL_GROUP_BY`, `STRICT_TRANS_TABLES` and `NO_ZERO_DATE` by default,
  none of which existed in 5.5; Codeface's 2013-era SQL does not satisfy them.
  This is what Travis was really buying by downgrading 5.6 -> 5.5.
- `root@localhost` authentication differs by how the package self-initialised,
  so the bootstrap *probes* for a working admin login (`-uroot`, then
  `-uroot -pcodeface`, then `/etc/mysql/debian.cnf`) rather than assuming one.

Schema loaded cleanly: **41 tables** in `codeface`, same again in
`codeface_testing`. Verified reachable from both runtimes independently —
Python (`MySQLdb`) and R (`RMySQL`) each report 41 tables.

**Node.js — second masked failure.** The first bootstrap run ended with
`npm: command not found`. The image had reported a successful build because
I had written the layer as

```
RUN apt-get install -y --no-install-recommends nodejs npm && ... || true
```

The trailing `|| true` applies to the whole `&&` chain, so it swallowed a real
apt failure. The underlying error was in the build log:

```
npm : Depends: node-gyp (>= 0.10.9) but it is not going to be installed
E: Unable to correct problems, you have held broken packages.
```

`--no-install-recommends` prevents `node-gyp`'s dependencies from resolving, so
`npm` is uninstallable. Rather than drop the flag (which drags in a large
recommends tree) I installed the **official Node 14.21.3 tarball**: it is the
newest Node line that still runs against bionic's glibc 2.27 (Node 16+ needs
2.28), and it bundles npm 6, which negotiates with the current registry far
better than bionic's npm 3.5.2. `nodejs` is symlinked to `node` because
Codeface invokes the binary under the Debian name.

Lesson recorded: **never terminate a Dockerfile `RUN` chain with `|| true`** —
it converts build failures into runtime failures far from their cause.

**Toolchain verification inside the container:**

| Component | Version | Note |
|---|---|---|
| `ctags-exuberant` | `Exuberant Ctags 5.9~svn20110310` | exactly satisfies the hard-coded assert |
| MySQL | 5.7.42 | 41 tables, reachable from Python and R |
| R | 3.6.3 | 32/32 required packages load |
| Python | 2.7.17 | `codeface` package imports |
| graphviz `dot` | 2.40.1 | cluster graph layout |
| `sloccount` | 2.26 | complexity stage |
| LuaTeX | 1.0.4 | PDF report stage |

## Phase 5 — Analysis run and the four defects it exposed

Strategy: run a **single-range smoke configuration** (`conf/flask-smoke.conf`,
3.0.0 -> 3.1.0) first so each debug cycle costs minutes, and only then the
full 7-range run.

### 5.1 `svglite` — a dependency no static analysis can find

First smoke run reached the *final* stage and died:

```
2026-08-11 10:28:38 [codeface.R] CRITICAL: there is no package called 'svglite'
  4: ggsave(file.path(graphdir, "ts_commits.svg"), g, width = 12, height = 8)
  6: svglite::svglite
```

`svglite` appears **nowhere** in Codeface's source — I re-scanned the whole
run-path closure for `library()`, `require()`, `requireNamespace()` *and*
`pkg::` references and the only namespace-qualified package is `igraph`.
The dependency is indirect: `analyse_ts.r` calls `ggsave()` with a `.svg`
filename, and ggplot2 dispatches on the extension to `svglite::svglite` at
runtime. ggplot2 declares svglite only under **Suggests** — precisely the
field my dependency restriction dropped.

So the 16x build-time saving had exactly one casualty, and it was invisible to
static analysis. Fixed by naming `svglite` explicitly in the required set
(upstream's `packages.r` did list it; my closure analysis is what lost it).
The general lesson: a source-derived dependency closure is a lower bound —
runtime dispatch on file extensions escapes it.

### 5.2 CLI option levels (my bug, not Codeface's)

`run_analysis.sh` invoked `codeface --recreate run ...` and argparse rejected
it. `-j/-l/-f` are *global* options that must precede the `run` subcommand,
while `--recreate/--no-report/--profile-r` belong to `run`. Fixed the wrapper
to take parallelism from `$JOBS` and forward the rest after `run`.

With that, the smoke run finished: **`=> Codeface run complete!`, exit 0.**

### 5.3 Upstream bug: project configs cannot enable `sloccount`

The run succeeded but two tables were empty. Investigating `sloccount_ts`,
I re-ran the complexity stage at `--loglevel devinfo` and saw:

```
[codeface.R] DEBUG: sloccount : FALSE
```

even though `conf/flask-smoke.conf` says `sloccount: true`. The cause is in
`codeface/R/config.r::load.config`:

```r
if(is.null(conf$understand)) { conf$understand <- FALSE }
if(is.null(conf$sloccount))  { conf$sloccount  <- FALSE }
...
conf <- c(conf, yaml.load_file(project.file))    # <-- appends, does not merge
```

The defaults are applied to the global config **before** the project file is
merged, and `c()` *concatenates* lists rather than merging them. The result
holds **two** elements named `sloccount`, and `conf$sloccount` returns the
first — the default `FALSE`. So `sloccount: true` in *any* project config was
silently discarded and `do.complexity.analysis()` always returned early.

Note the Python side does not have this bug: `configuration.py` uses
`dict.update()`, which replaces correctly. Only the R loader is affected, and
only for the two keys defaulted before the merge.

**Patch:** replace duplicate keys instead of appending —
`project.conf <- yaml.load_file(project.file); conf[names(project.conf)] <- project.conf`.
Result: `sloccount : TRUE`, and the stage reports `Analysing 41 code samples`.

### 5.4 Upstream bug: sloccount races itself under `-j > 1`

With sloccount finally enabled, the log showed
`running command '/usr/bin/sloccount ...' had status 1` and only **6 of 41**
samples landed in the database.

sloccount alone worked (10 075 SLOC for Flask 3.1.0, exit 0), and so did two
sequential runs. Running four concurrently reproduced it immediately:

```
mkdir: cannot create directory '/root/.slocdata': File exists
run1 EXIT=1  run2 EXIT=1  run3 EXIT=1  run4 EXIT=1
```

`gather.sloccount.results()` in `codeface/R/sloccount.r` invokes sloccount
without `--datadir`, so every instance uses the single default `~/.slocdata`.
`do.complexity.analysis()` calls it from inside `mclapply.db()`, so with
`-j > 1` the instances race and all but one abort. The failures were invisible
because `do.system` redirects stderr to `/dev/null`; the only symptom was a
sparsely populated `sloccount_ts`.

**Patch:** give each invocation its own data directory. One wrinkle found by
testing: sloccount requires the directory to *already exist* — passing a
non-existent path fails with `Error: <path> is not a directory` — so the fix
uses `tempfile()` + `dir.create()` + `on.exit(unlink(...))`.

Verified: 4 concurrent runs all exit 0, and re-running the complexity stage
with `-j 4` wrote **41 of 41** samples (previously 6).
