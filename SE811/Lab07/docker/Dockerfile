# ---------------------------------------------------------------------------
# Codeface (siemens/codeface, archived 2022) -- modern reproducible build
#
# Codeface targets Ubuntu 14.04/16.04, Python 2.7, R 3.x and MySQL 5.5.
# None of that exists on a 2026 host, so the legacy runtime is reconstructed
# inside a container pinned to the last distribution that still carries a
# packaged Python 2.7 *and* still has live APT archives: Ubuntu 18.04.
#
# Version pinning rationale:
#   * Ubuntu 18.04  - last release with python2.7 in main + live archive.ubuntu.com
#   * R 3.6.3       - newest R in CRAN's frozen bionic-cran35 archive; also the
#                     R generation Codeface's last commit (2019) was written for.
#   * CRAN snapshot 2020-04-01 - Posit Package Manager date-pinned mirror, taken
#                     just before R 4.0.0 shipped, so every package resolves to
#                     a version that still declares R (>= 3.x) compatibility.
#   * Bioconductor 3.10 - the Bioc release matched to R 3.6.
#   * MySQL 5.7     - bionic's default; strict SQL modes disabled to emulate 5.5.
# ---------------------------------------------------------------------------
FROM ubuntu:18.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=UTC

# ---------------------------------------------------------------------------
# 1. Base toolchain, analysis binaries and -dev headers for the R/Python
#    packages that build native code.
# ---------------------------------------------------------------------------
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
        ca-certificates curl wget gnupg dirmngr lsb-release apt-transport-https \
        build-essential gfortran pkg-config make cmake \
        git subversion \
        python2.7 python2.7-dev libpython2.7-dev \
        exuberant-ctags sloccount graphviz doxygen astyle xsltproc \
        libgraphviz-dev libxml2-dev libxslt1-dev libcurl4-openssl-dev \
        libssl-dev libssh2-1-dev libyaml-dev libcairo2-dev libxt-dev \
        libhunspell-dev libpoppler-dev libpoppler-glib-dev libarchive13 \
        libfontconfig1-dev libfreetype6-dev libpng-dev libjpeg-dev libtiff5-dev \
        zlib1g-dev libbz2-dev liblzma-dev libpcre3-dev \
        vim less procps net-tools iproute2 sudo unzip \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 2. MySQL 5.7 (stand-in for the EOL MySQL 5.5 Codeface was written against)
# ---------------------------------------------------------------------------
RUN echo "mysql-server mysql-server/root_password password codeface" | debconf-set-selections && \
    echo "mysql-server mysql-server/root_password_again password codeface" | debconf-set-selections && \
    apt-get update -qq && apt-get install -y --no-install-recommends \
        mysql-server mysql-client libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Emulate MySQL 5.5 semantics: 5.7 turns on ONLY_FULL_GROUP_BY /
# STRICT_TRANS_TABLES / NO_ZERO_DATE by default, which rejects the INSERTs and
# GROUP BY queries that Codeface's 2013-era SQL depends on.
RUN printf '%s\n' \
        '[mysqld]' \
        'sql_mode=' \
        'character-set-server=utf8' \
        'collation-server=utf8_general_ci' \
        'max_allowed_packet=256M' \
        'innodb_buffer_pool_size=512M' \
        'socket=/var/run/mysqld/mysqld.sock' \
        '' \
        '[client]' \
        'socket=/var/run/mysqld/mysqld.sock' \
        'default-character-set=utf8' \
        > /etc/mysql/conf.d/codeface.cnf

# ---------------------------------------------------------------------------
# 3. LaTeX (lualatex) for Codeface's PDF report stage
# ---------------------------------------------------------------------------
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
        texlive-luatex texlive-latex-base texlive-latex-recommended \
        texlive-fonts-recommended lmodern \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 5. R 3.6.3 from CRAN's frozen bionic-cran35 archive
# ---------------------------------------------------------------------------
RUN wget -qO /etc/apt/trusted.gpg.d/cran_ubuntu_key.asc \
        https://cloud.r-project.org/bin/linux/ubuntu/marutter_pubkey.asc && \
    echo "deb https://cloud.r-project.org/bin/linux/ubuntu bionic-cran35/" \
        > /etc/apt/sources.list.d/cran.list && \
    apt-get update -qq && apt-get install -y --no-install-recommends \
        r-base r-base-dev r-base-core \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# 6. Python 2.7 tooling. Bionic's python-pip is too old to talk to today's
#    PyPI (TLS + JSON API), so pip is bootstrapped from the pypa-maintained
#    Python 2.7 installer instead.
# ---------------------------------------------------------------------------
RUN wget -qO /tmp/get-pip.py https://bootstrap.pypa.io/pip/2.7/get-pip.py && \
    python2.7 /tmp/get-pip.py "pip==20.3.4" "setuptools==44.1.1" "wheel==0.37.1" && \
    rm -f /tmp/get-pip.py && \
    ln -sf /usr/bin/python2.7 /usr/local/bin/python && \
    python2.7 -m pip --version

COPY python_requirements_pinned.txt /tmp/python_requirements_pinned.txt
RUN python2.7 -m pip install --no-cache-dir -r /tmp/python_requirements_pinned.txt && \
    python2.7 -c "import MySQLdb, ctags, yaml, progressbar, jira; print('python deps OK')"

# ---------------------------------------------------------------------------
# 7. R packages: CRAN pinned to a 2020-04-01 snapshot, Bioconductor to 3.10.
# ---------------------------------------------------------------------------
#    PPM serves prebuilt bionic binaries for most CRAN packages at this
#    snapshot. Those binaries were linked on a fuller build image than this
#    one, so their shared-library dependencies must exist here or dyn.load()
#    fails at *load* time even though "installation" reported success --
#    e.g. igraph.so has NEEDED entries for libgmp.so.10 and libglpk.so.40.
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
        libglpk-dev libgmp-dev libmpfr-dev libicu-dev \
        libblas-dev liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

#    The required set is a separate layer from the best-effort extras so an
#    optional failure cannot invalidate the core cache.
COPY install_r_packages.R /tmp/install_r_packages.R
RUN RPKG_MODE=required Rscript /tmp/install_r_packages.R
RUN RPKG_MODE=optional Rscript /tmp/install_r_packages.R; \
    rm -f /tmp/install_r_packages.R

#    shinyGridster (Shiny "dashboard" app only) is the one front-end package
#    that never reached CRAN, so it must come from source. Upstream installs it
#    with devtools::install_github, which would pull the whole devtools tree
#    into the image; fetching the tarball and running R CMD INSTALL is
#    equivalent and far cheaper. Best-effort: the front end is not required for
#    `codeface run`.
RUN set -e; \
    tmp=$(mktemp -d); \
    if wget -qO "$tmp/gridster.tar.gz" \
         https://codeload.github.com/wch/shiny-gridster/tar.gz/refs/heads/master; then \
        tar -xzf "$tmp/gridster.tar.gz" -C "$tmp" && \
        R CMD INSTALL "$tmp/shiny-gridster-master" || \
        echo "WARNING: shinyGridster install failed (dashboard app unavailable)"; \
    else \
        echo "WARNING: could not fetch shinyGridster (dashboard app unavailable)"; \
    fi; \
    rm -rf "$tmp"; \
    Rscript -e 'cat("shinyGridster available:", requireNamespace("shinyGridster", quietly=TRUE), "\n")'

# ---------------------------------------------------------------------------
# 8. Node.js for the ID service.
#
#    Deliberately placed after the R layers so that revising it does not
#    invalidate the expensive package builds above.
#
#    bionic's own `npm` package cannot be installed under
#    --no-install-recommends -- apt reports
#      "npm : Depends: node-gyp (>= 0.10.9) but it is not going to be installed"
#    -- and its npm 3.5.2 is in any case too old to resolve today's registry
#    metadata. The official Node 14 tarball is used instead: it is the newest
#    line that still runs against bionic's glibc 2.27, and it bundles npm 6.
# ---------------------------------------------------------------------------
ENV NODE_VERSION=14.21.3
RUN wget -qO /tmp/node.tar.xz \
        "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" && \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
        --exclude=CHANGELOG.md --exclude=LICENSE --exclude=README.md && \
    rm -f /tmp/node.tar.xz && \
    ln -sf /usr/local/bin/node /usr/local/bin/nodejs && \
    node --version && nodejs --version && npm --version

# ---------------------------------------------------------------------------
# 9. Shiny Server for the web frontend.
#
#    docs/webserver.md wants a custom fork (JohannesEbke/shiny-server, branch
#    no-su) installed into a bundled Node.js 0.10.13 -- a 2013 runtime that no
#    longer builds, from a fork that has since disappeared. The official Shiny
#    Server reads the same site_dir/directory_index configuration, and RStudio
#    still publishes a bionic build.
#
#    It is needed because the frontend's breadcrumb links are relative
#    ("../dashboard/?projectid=2"), so each app must be mounted under its own
#    URL path; running a single app with runApp() makes those links 404.
#
#    Best-effort: the frontend is not required for `codeface run`.
# ---------------------------------------------------------------------------
ENV SHINY_SERVER_VERSION=1.5.20.1002
RUN set -e; \
    if wget -qO /tmp/shiny-server.deb \
         "https://download3.rstudio.org/ubuntu-18.04/x86_64/shiny-server-${SHINY_SERVER_VERSION}-amd64.deb"; then \
        apt-get update -qq && \
        (dpkg -i /tmp/shiny-server.deb || apt-get -f install -y) && \
        rm -rf /var/lib/apt/lists/*; \
    else \
        echo "WARNING: could not fetch Shiny Server (web frontend unavailable)"; \
    fi; \
    rm -f /tmp/shiny-server.deb; \
    command -v shiny-server >/dev/null && shiny-server --version || true

# ---------------------------------------------------------------------------
# 10. Runtime wiring
# ---------------------------------------------------------------------------
RUN mkdir -p /var/run/mysqld /work /codeface && \
    chown -R mysql:mysql /var/run/mysqld

COPY start_services.sh /usr/local/bin/start_services.sh
RUN chmod +x /usr/local/bin/start_services.sh

WORKDIR /codeface
CMD ["sleep", "infinity"]
