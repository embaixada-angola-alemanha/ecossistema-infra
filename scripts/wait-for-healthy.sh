#!/usr/bin/env bash
# =============================================================================
# Ecossistema Digital — Wait for all services to report healthy
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

SERVICES=(postgres redis keycloak minio mailhog nginx)
MAX_WAIT=180  # seconds
INTERVAL=5

elapsed=0

echo "Waiting up to ${MAX_WAIT}s for services to be healthy..."

while [ $elapsed -lt $MAX_WAIT ]; do
    all_healthy=true

    for svc in "${SERVICES[@]}"; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "ecossistema-${svc}" 2>/dev/null || echo "not_found")
        if [ "$status" != "healthy" ]; then
            all_healthy=false
            break
        fi
    done

    if $all_healthy; then
        echo "All services are healthy! (${elapsed}s)"
        exit 0
    fi

    sleep $INTERVAL
    elapsed=$((elapsed + INTERVAL))

    # Progress
    statuses=""
    for svc in "${SERVICES[@]}"; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "ecossistema-${svc}" 2>/dev/null || echo "?")
        case $status in
            healthy)   statuses="$statuses $svc:OK" ;;
            starting)  statuses="$statuses $svc:..." ;;
            unhealthy) statuses="$statuses $svc:FAIL" ;;
            *)         statuses="$statuses $svc:?" ;;
        esac
    done
    echo "[${elapsed}s]${statuses}"
done

echo "ERROR: Timed out after ${MAX_WAIT}s. Not all services are healthy."
docker compose ps
exit 1
