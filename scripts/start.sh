#!/usr/bin/env bash
# =============================================================================
# Ecossistema Digital — Start all infrastructure services
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Ecossistema Digital — Starting infrastructure ==="
echo ""

docker compose up -d

echo ""
echo "=== Waiting for all services to be healthy ==="
bash "$SCRIPT_DIR/wait-for-healthy.sh"

echo ""
echo "=== All services are running ==="
echo ""
echo "  PostgreSQL : localhost:5432"
echo "  Redis      : localhost:6379"
echo "  Keycloak   : http://localhost:8080"
echo "  MinIO API  : http://localhost:9000"
echo "  MinIO UI   : http://localhost:9001"
echo "  MailHog    : http://localhost:8025"
echo "  Nginx      : http://localhost"
echo ""
