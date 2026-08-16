## ---------------------------------------------------------------------------
## R dependency installation for Codeface, replacing upstream packages.r.
##
## Why upstream packages.r cannot be used verbatim:
##   * it calls biocLite() from bioconductor.org/biocLite.R, which was retired
##     in 2019 (Bioconductor 3.8) and now only prints an error;
##   * it installs from live CRAN HEAD, whose current package versions require
##     R >= 4.x and therefore refuse to install on R 3.6;
##   * it pulls four packages from GitHub via devtools::install_github(), which
##     needs network + auth at build time and is only used by the mailing-list
##     and Shiny front-end paths, not by `codeface run`;
##   * it passes dependencies=TRUE, which resolves Suggests as well. On the
##     pinned snapshot that expands the 29 roots into a 1544-package closure
##     (devtools, usethis, rmarkdown, ...). Restricting to the hard dependency
##     fields yields 96 packages -- the same functionality, 16x less to build.
##
## CRAN is pinned to a Posit Package Manager snapshot taken just before R 4.0.0
## shipped, and Bioconductor to release 3.10 (the release matched to R 3.6).
## Both are immutable, so the build is reproducible. Note that PPM no longer
## serves precompiled binaries for these old snapshots, so everything is built
## from source -- hence the explicit parallelism below.
##
## Mode is selected with RPKG_MODE=required|optional.
## ---------------------------------------------------------------------------

options(warn = 1)

MODE          <- Sys.getenv("RPKG_MODE", "required")
CRAN.SNAPSHOT <- Sys.getenv("CRAN_SNAPSHOT", "2020-04-01")
BIOC.VERSION  <- Sys.getenv("BIOC_VERSION", "3.10")

## PPM serves platform binaries only when the client advertises its platform.
## Harmless to keep even though these snapshots are source-only today.
options(HTTPUserAgent = sprintf(
    "R/%s R (%s)", getRversion(),
    paste(getRversion(), R.version["platform"], R.version["arch"], R.version["os"])))

options(repos = c(
    CRAN     = sprintf("https://packagemanager.posit.co/cran/__linux__/bionic/%s", CRAN.SNAPSHOT),
    BioCsoft = sprintf("https://bioconductor.org/packages/%s/bioc", BIOC.VERSION),
    BioCann  = sprintf("https://bioconductor.org/packages/%s/data/annotation", BIOC.VERSION),
    BioCexp  = sprintf("https://bioconductor.org/packages/%s/data/experiment", BIOC.VERSION)
))

## Only hard dependencies -- see header.
DEP.FIELDS <- c("Depends", "Imports", "LinkingTo")

num.cores <- tryCatch(parallel::detectCores(logical = TRUE), error = function(e) 1L)
if (is.na(num.cores) || num.cores < 1L) num.cores <- 1L

## Packages reached by the `codeface run` pipeline, i.e. the transitive
## source() closure of cluster/persons.r + complexity.r + analyse_ts.r.
required.cran <- c(
    ## infrastructure
    "optparse", "logging", "yaml", "stringr", "RMySQL", "RCurl", "RJSONIO", "rjson",
    ## data wrangling
    "plyr", "reshape", "data.table", "zoo", "xts", "lubridate",
    ## graphs / networks
    "igraph",
    ## plotting / reporting
    ## svglite is NOT referenced anywhere in Codeface's source, so the static
    ## source() closure misses it: analyse_ts.r calls ggsave(".svg"), and
    ## ggplot2 dispatches on the extension to svglite::svglite at runtime.
    ## ggplot2 declares svglite only under Suggests, which this script
    ## deliberately does not resolve -- hence it must be named explicitly.
    "ggplot2", "svglite", "scales", "gridExtra", "xtable", "colorspace",
    ## analytics used by the pipeline
    "arules", "corrgram", "dtw", "ineq", "lsa", "tm", "markovchain",
    "psych", "robustbase"
)

## Bioconductor: graph + Rgraphviz (cluster layout), BiRewire (null-model
## rewiring used by the socio-technical stage).
required.bioc <- c("graph", "Rgraphviz", "BiRewire")

## Not on the `run` path: conway / mailing-list / Shiny front-end extras.
## Installed best-effort in a separate image layer.
##
## shinybootstrap2 is needed by every Shiny app (they wrap their UI in
## shinybootstrap2::withBootstrap2). Upstream packages.r installs it with
## devtools::install_github("rstudio/shinybootstrap2"), which no longer
## resolves -- that repository now 404s. It is on CRAN, so the pinned snapshot
## provides it. shinyGridster (dashboard app only) is genuinely GitHub-only and
## is installed from a source tarball in the Dockerfile.
optional.pkgs <- c("testthat", "png", "corrplot", "shiny", "shinybootstrap2",
                   "hashmap", "randomForest")

install.set <- function(pkgs, label) {
    todo <- pkgs[!(pkgs %in% rownames(installed.packages()))]
    if (length(todo) == 0) {
        cat("== ", label, ": already satisfied\n", sep = "")
        return(invisible())
    }
    cat("\n== Installing ", label, " (", length(todo), " roots): ",
        paste(todo, collapse = ", "), "\n", sep = "")
    install.packages(todo, dependencies = DEP.FIELDS, Ncpus = num.cores)
}

## Report *why* a package will not load. install.packages() happily reports
## success for a prebuilt binary whose shared-library dependencies are absent
## from this image; the failure only shows up here, at dyn.load() time.
load.error <- new.env(parent = emptyenv())
loadable <- function(p) {
    ok <- tryCatch(
        suppressWarnings(suppressPackageStartupMessages(
            requireNamespace(p, quietly = TRUE))),
        error = function(e) { assign(p, conditionMessage(e), envir = load.error); FALSE })
    if (!ok && !exists(p, envir = load.error)) {
        assign(p, "package not installed", envir = load.error)
    }
    isTRUE(ok)
}

report.failures <- function(pkgs) {
    for (p in pkgs) {
        msg <- if (exists(p, envir = load.error)) get(p, envir = load.error) else "unknown"
        cat("  - ", p, ": ", gsub("\n", " ", msg), "\n", sep = "")
    }
}

cat("== R", as.character(getRversion()), "| CRAN snapshot", CRAN.SNAPSHOT,
    "| Bioc", BIOC.VERSION, "| mode:", MODE, "| cores:", num.cores, "==\n")

if (identical(MODE, "optional")) {
    install.set(optional.pkgs, "optional packages")
    missing.opt <- optional.pkgs[!vapply(optional.pkgs, loadable, logical(1))]
    if (length(missing.opt) > 0) {
        cat("NOTE: optional packages unavailable:\n")
        report.failures(missing.opt)
    } else {
        cat("All optional packages installed.\n")
    }
    quit(status = 0, save = "no")   # never fail the build on optional extras
}

install.set(required.cran, "required CRAN packages")
install.set(required.bioc, "required Bioconductor packages")

cat("\n===== verification =====\n")
must <- c(required.cran, required.bioc)
missing.must <- must[!vapply(must, loadable, logical(1))]

if (length(missing.must) > 0) {
    cat("ERROR: required packages failed to install or load:\n")
    report.failures(missing.must)
    quit(status = 1, save = "no")
}

cat("All ", length(must), " required R packages installed and loadable.\n", sep = "")
cat("Total packages in library: ", nrow(installed.packages()), "\n", sep = "")
