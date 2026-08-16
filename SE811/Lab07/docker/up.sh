#!/bin/bash
# ---------------------------------------------------------------------------
# Build the image (if needed) and start the long-lived Codeface container.
# Run from the repository root's parent, i.e. .../Lab07/
#
#   ./docker/up.sh            # start (build if image missing)
#   ./docker/up.sh --rebuild  # force image rebuild
#
# The Codeface checkout and the working data are bind-mounted rather than
# baked in, so source patches take effect immediately without a rebuild.
# ---------------------------------------------------------------------------
set -eu

LAB_ROOT=${LAB_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
IMAGE=${IMAGE:-codeface:bionic}
NAME=${NAME:-codeface}

if [ "${1:-}" = "--rebuild" ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "==> building $IMAGE"
    docker build -t "$IMAGE" "$LAB_ROOT/docker"
fi

if docker inspect "$NAME" >/dev/null 2>&1; then
    echo "==> container '$NAME' exists; starting it"
    docker start "$NAME" >/dev/null
else
    echo "==> creating container '$NAME'"
    docker run -d --name "$NAME" \
        -v "$LAB_ROOT/codeface:/codeface" \
        -v "$LAB_ROOT/work:/work" \
        -v "$LAB_ROOT/docker:/scripts" \
        -p 8081:8081 \
        --shm-size=1g \
        "$IMAGE" sleep infinity >/dev/null
fi

echo "==> bootstrapping"
docker exec "$NAME" bash /scripts/bootstrap_codeface.sh

cat <<EOF

Container '$NAME' is ready.

  Run the analysis:
    docker exec $NAME bash /scripts/run_analysis.sh conf/flask.conf -j4

  Inspect the database:
    docker exec $NAME bash /scripts/collect_evidence.sh flask

  Shell:
    docker exec -it $NAME bash
EOF
