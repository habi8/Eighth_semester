#!/bin/bash
# ---------------------------------------------------------------------------
# Serve the Codeface web frontend on http://localhost:8081/apps/projects/
#
#   serve_frontend.sh              # all apps via Shiny Server (recommended)
#   serve_frontend.sh single <app> # one app at /, via `codeface dynamic`
#
# Why Shiny Server and not just `codeface dynamic`:
#   The frontend's breadcrumb navigation uses *relative* links
#   ("../dashboard/?projectid=2"), so every app must be mounted under its own
#   URL path beneath a shared parent. `codeface dynamic` runs runApp(), which
#   mounts a single app at "/" -- the apps load, but clicking through to a
#   project gives 404 because ../dashboard/ resolves to nothing.
#
#   The route in docs/webserver.md is dead: it wants a custom shiny-server fork
#   (JohannesEbke/shiny-server, branch no-su) inside a bundled Node.js 0.10.13.
#   The official Shiny Server understands the same site_dir/directory_index
#   configuration, so it is used instead.
#
# Run in the foreground (Ctrl-C to stop); use `docker exec -d` to detach.
# ---------------------------------------------------------------------------
set -u
CODEFACE_DIR=${CODEFACE_DIR:-/codeface}
PORT=${PORT:-8081}
CONF=${SHINY_CONF:-/scripts/shiny-server-codeface.conf}

cd "$CODEFACE_DIR" || exit 1

# The frontend reads the analysis results straight out of MySQL.
/usr/local/bin/start_services.sh >/dev/null 2>&1

# --- single-app mode -------------------------------------------------------
if [ "${1:-}" = "single" ]; then
    APP=${2:-projects}
    echo "single-app mode: http://localhost:$PORT/  (app: $APP)"
    echo "note: cross-app navigation links will 404 in this mode"
    exec codeface dynamic "$APP" -c "$CODEFACE_DIR/codeface.conf" -p "$PORT"
fi

# --- Shiny Server mode -----------------------------------------------------
if ! command -v shiny-server >/dev/null 2>&1; then
    echo "ERROR: shiny-server is not installed in this image." >&2
    echo "       Rebuild the image, or use: serve_frontend.sh single projects" >&2
    exit 1
fi

# Shiny Server refuses to launch workers as root, so it drops to the `shiny`
# account. Give that account the two directories it must write to.
mkdir -p /var/log/shiny-server "$CODEFACE_DIR/log"
chown -R shiny:shiny /var/log/shiny-server 2>/dev/null || true
chmod 1777 "$CODEFACE_DIR/log" 2>/dev/null || true

# Stop a previous instance, matching the running node process rather than the
# string "shiny-server" (which would also match this script's own command line).
ps -eo pid,args | grep "[s]hiny-server/lib/main.js" | awk '{print $1}' \
    | xargs -r kill 2>/dev/null
sleep 1

echo "=============================================================="
echo " Codeface web frontend  (Shiny Server)"
echo "   open : http://localhost:$PORT/apps/projects/"
echo "   apps : projects dashboard details plots timeseries timezones"
echo "   index: http://localhost:$PORT/apps/"
echo "=============================================================="
echo

exec shiny-server "$CONF"
