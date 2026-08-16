#!/bin/bash
# ---------------------------------------------------------------------------
# Run a Codeface analysis inside the container.
#
#   run_analysis.sh <project-conf> [extra args for the `run` subcommand...]
#
# e.g.  JOBS=4 run_analysis.sh conf/flask.conf --recreate
#
# Note the CLI splits its options across two levels: -j/-l/-f are *global*
# options that must precede the `run` subcommand, while --recreate,
# --no-report, --profile-r etc. belong to `run` itself. Parallelism is
# therefore taken from $JOBS and everything else is forwarded after `run`.
#
# Assumes bootstrap_codeface.sh has already been run at least once.
# ---------------------------------------------------------------------------
set -u
CODEFACE_DIR=${CODEFACE_DIR:-/codeface}
WORK_DIR=${WORK_DIR:-/work}
RESDIR=${RESDIR:-$WORK_DIR/res}
GITDIR=${GITDIR:-$WORK_DIR/git-repos}

PROJECT_CONF=${1:?usage: run_analysis.sh <project-conf> [extra run args]}
shift || true
JOBS=${JOBS:-2}

cd "$CODEFACE_DIR" || exit 1
mkdir -p "$RESDIR" "$GITDIR" "$CODEFACE_DIR/log"

# Make sure MySQL + the ID service are up.
/usr/local/bin/start_services.sh || exit 1

echo
echo "=============================================================="
echo " codeface run"
echo "   project conf : $PROJECT_CONF"
echo "   results dir  : $RESDIR"
echo "   git dir      : $GITDIR"
echo "   jobs         : $JOBS"
echo "   extra args   : $*"
echo "=============================================================="
echo

exec codeface -j "$JOBS" run \
    -c "$CODEFACE_DIR/codeface.conf" \
    -p "$CODEFACE_DIR/$PROJECT_CONF" \
    "$@" \
    "$RESDIR" "$GITDIR"
