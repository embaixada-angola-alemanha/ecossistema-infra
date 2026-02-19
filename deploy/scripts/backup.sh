#!/bin/bash
# =============================================================================
# Ecossistema Digital — Daily Database Backup
# Runs via cron: 0 2 * * * (daily at 2 AM)
# =============================================================================

set -euo pipefail

BACKUP_DIR="/opt/ecossistema/backups"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

echo "=== Database Backup — ${DATE} ==="

mkdir -p ${BACKUP_DIR}

# Backup function
backup_env() {
    local ENV=$1
    local PG_PORT=$2
    local PG_PASSWORD=$3

    echo "--- Backing up ${ENV} databases ---"

    for DB in sgc_db si_db wn_db gpj_db keycloak_db; do
        BACKUP_FILE="${BACKUP_DIR}/${ENV}_${DB}_${DATE}.sql.gz"
        echo "  Dumping ${DB}..."
        PGPASSWORD="${PG_PASSWORD}" pg_dump \
            -h 127.0.0.1 \
            -p ${PG_PORT} \
            -U ecossistema \
            -d ${DB} \
            --no-owner \
            --no-privileges \
            | gzip > "${BACKUP_FILE}"
        echo "  → ${BACKUP_FILE} ($(du -h ${BACKUP_FILE} | cut -f1))"
    done
}

# Read credentials from env files
if [ -f /opt/ecossistema/repos/ecossistema-infra/deploy/.env.staging ]; then
    source /opt/ecossistema/repos/ecossistema-infra/deploy/.env.staging
    backup_env "staging" "${POSTGRES_PORT}" "${POSTGRES_PASSWORD}"
fi

if [ -f /opt/ecossistema/repos/ecossistema-infra/deploy/.env.production ]; then
    source /opt/ecossistema/repos/ecossistema-infra/deploy/.env.production
    backup_env "production" "${POSTGRES_PORT}" "${POSTGRES_PASSWORD}"
fi

# Clean old backups
echo "--- Cleaning backups older than ${RETENTION_DAYS} days ---"
find ${BACKUP_DIR} -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "=== Backup complete ==="
