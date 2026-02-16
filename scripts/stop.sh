#!/usr/bin/env bash
# =============================================================================
# Ecossistema Digital — Stop all infrastructure services
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=== Ecossistema Digital — Stopping infrastructure ==="
docker compose down
echo "=== All services stopped ==="
