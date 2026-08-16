#!/bin/bash
# ---------------------------------------------------------------------------
# One-time (idempotent) initialisation of the Codeface working tree inside the
# container:
#   1. start MySQL
#   2. create the codeface / codeface_testing databases + user, load the schema
#   3. install the Node.js ID service dependencies
#   4. install the codeface Python package in development mode
#
# This replaces integration-scripts/setup_database.sh +
# install_codeface_python.sh + install_codeface_node.sh, which assume a
# Vagrant VM with a `vagrant` user and passwordless sudo.
# ---------------------------------------------------------------------------
set -u
CODEFACE_DIR=${CODEFACE_DIR:-/codeface}
cd "$CODEFACE_DIR" || exit 1

log() { echo "[bootstrap] $*"; }
fail() { echo "[bootstrap] ERROR: $*" >&2; exit 1; }

# --- 1. MySQL --------------------------------------------------------------
mkdir -p /var/run/mysqld /var/log/mysql
chown -R mysql:mysql /var/run/mysqld /var/log/mysql

if ! mysqladmin ping --silent 2>/dev/null; then
    log "starting MySQL ..."
    mysqld_safe --skip-syslog >/var/log/mysql/mysqld_safe.log 2>&1 &
    for _ in $(seq 1 60); do
        mysqladmin ping --silent 2>/dev/null && break
        sleep 1
    done
fi
mysqladmin ping --silent 2>/dev/null || fail "MySQL did not start"
ln -sf /var/run/mysqld/mysqld.sock /tmp/mysql.sock 2>/dev/null || true

# --- 2. databases, user, schema -------------------------------------------
# Depending on how the mysql-server package initialised itself, root@localhost
# may use auth_socket, the preseeded password, or neither. Probe for a working
# administrative invocation instead of assuming one.
ADMIN=""
for candidate in "mysql -uroot" "mysql -uroot -pcodeface" \
                 "mysql --defaults-file=/etc/mysql/debian.cnf"; do
    if $candidate -e "SELECT 1;" >/dev/null 2>&1; then
        ADMIN="$candidate"; break
    fi
done
[ -n "$ADMIN" ] || fail "no working MySQL administrative login found"
log "MySQL $($ADMIN -N -B -e 'SELECT VERSION();' 2>/dev/null) is running"

log "creating databases and user ..."
$ADMIN <<'SQL' || exit 1
CREATE DATABASE IF NOT EXISTS codeface;
CREATE DATABASE IF NOT EXISTS codeface_testing;
CREATE USER IF NOT EXISTS 'codeface'@'localhost' IDENTIFIED BY 'codeface';
CREATE USER IF NOT EXISTS 'codeface'@'127.0.0.1' IDENTIFIED BY 'codeface';
CREATE USER IF NOT EXISTS 'codeface'@'%' IDENTIFIED BY 'codeface';
GRANT ALL PRIVILEGES ON *.* TO 'codeface'@'localhost' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON *.* TO 'codeface'@'127.0.0.1' WITH GRANT OPTION;
GRANT ALL PRIVILEGES ON *.* TO 'codeface'@'%' WITH GRANT OPTION;
FLUSH PRIVILEGES;
SQL

DATAMODEL="datamodel/codeface_schema.sql"
[ -f "$DATAMODEL" ] || fail "$DATAMODEL not found (wrong working directory?)"

log "loading schema into 'codeface' ..."
mysql -ucodeface -pcodeface < "$DATAMODEL" 2>/dev/null || fail "schema load failed"

log "loading schema into 'codeface_testing' ..."
sed -e 's/codeface/codeface_testing/g' "$DATAMODEL" \
    | mysql -ucodeface -pcodeface 2>/dev/null || fail "testing schema load failed"

TABLES=$(mysql -N -B -ucodeface -pcodeface -e \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='codeface';" 2>/dev/null)
log "schema loaded: $TABLES tables in database 'codeface'"

# --- 3. ID service dependencies -------------------------------------------
if [ ! -d id_service/node_modules ]; then
    log "installing ID service npm dependencies ..."
    ( cd id_service && npm install --no-bin-links --no-audit --no-fund 2>&1 | tail -5 )
else
    log "ID service node_modules already present"
fi

# --- 4. codeface python package -------------------------------------------
log "installing codeface (development mode) ..."
python2.7 setup.py -q develop 2>&1 | tail -5
command -v codeface >/dev/null || fail "codeface entry point not on PATH"
log "codeface CLI: $(command -v codeface)"

log "bootstrap complete"
