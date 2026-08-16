#!/bin/bash
# ---------------------------------------------------------------------------
# Bring up the backing services Codeface needs inside the container:
#   1. MySQL 5.7 (the results database)
#   2. the Node.js "ID service" (person/identity de-duplication REST service)
#
# Idempotent: safe to re-run, will not start a second copy of either service.
# ---------------------------------------------------------------------------
set -u

CODEFACE_DIR=${CODEFACE_DIR:-/codeface}
CONF=${CONF:-$CODEFACE_DIR/codeface.conf}

log() { echo "[services] $*"; }

# --- 1. MySQL --------------------------------------------------------------
mkdir -p /var/run/mysqld /var/log/mysql
chown -R mysql:mysql /var/run/mysqld /var/log/mysql

if mysqladmin ping --silent 2>/dev/null; then
    log "MySQL already running"
else
    log "starting MySQL ..."
    mysqld_safe --skip-syslog >/var/log/mysql/mysqld_safe.log 2>&1 &
    for i in $(seq 1 60); do
        if mysqladmin ping --silent 2>/dev/null; then break; fi
        sleep 1
    done
    if mysqladmin ping --silent 2>/dev/null; then
        log "MySQL is up ($(mysql -N -B -e 'SELECT VERSION();' 2>/dev/null))"
    else
        log "ERROR: MySQL failed to start; see /var/log/mysql/"
        exit 1
    fi
fi

# Provide the socket path older Codeface code/hacks expect.
ln -sf /var/run/mysqld/mysqld.sock /tmp/mysql.sock 2>/dev/null || true

# --- 2. ID service ---------------------------------------------------------
if curl -s -o /dev/null --max-time 2 http://localhost:8080/post_user_id; then
    log "ID service already running on :8080"
else
    log "starting Node.js ID service ..."
    cd "$CODEFACE_DIR/id_service" || exit 1
    nohup nodejs id_service.js "$CONF" >/var/log/id_service.log 2>&1 &
    for i in $(seq 1 30); do
        if curl -s -o /dev/null --max-time 2 http://localhost:8080/getUserID 2>/dev/null \
           || grep -q "Listening" /var/log/id_service.log 2>/dev/null; then
            break
        fi
        sleep 1
    done
    sleep 1
    if pgrep -f "id_service.js" >/dev/null; then
        log "ID service is up (log: /var/log/id_service.log)"
    else
        log "ERROR: ID service failed to start:"
        tail -20 /var/log/id_service.log
        exit 1
    fi
fi

log "all services ready"
