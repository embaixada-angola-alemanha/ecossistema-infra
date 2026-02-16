#!/usr/bin/env bash
# =============================================================================
# Ecossistema Digital — Reset all infrastructure (destroys data!)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Ecossistema Digital — RESET ==="
echo "WARNING: This will destroy all data (databases, files, cache)!"
echo ""
read -p "Are you sure? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo "Stopping services..."
docker compose down -v

echo "Removing data volumes..."
docker volume rm ecossistema_postgres_data ecossistema_redis_data ecossistema_minio_data 2>/dev/null || true

echo ""
echo "=== Reset complete. Run ./scripts/start.sh to start fresh. ==="
