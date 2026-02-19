#!/bin/bash
# =============================================================================
# Ecossistema Digital — Deploy Script
# Usage: ./deploy.sh [staging|production] [--build] [--pull]
# =============================================================================

set -euo pipefail

ENV=${1:-staging}
BUILD=false
PULL=false

shift || true
for arg in "$@"; do
    case $arg in
        --build) BUILD=true ;;
        --pull) PULL=true ;;
    esac
done

DEPLOY_DIR="/opt/ecossistema"
COMPOSE_DIR="${DEPLOY_DIR}/repos/ecossistema-infra/deploy"
ENV_FILE="${COMPOSE_DIR}/.env.${ENV}"

if [ ! -f "${ENV_FILE}" ]; then
    echo "ERROR: ${ENV_FILE} not found"
    exit 1
fi

echo "=== Deploying ${ENV} environment ==="

# 1. Pull latest code
if [ "$PULL" = true ]; then
    echo "--- Pulling latest code ---"
    for REPO_DIR in ${DEPLOY_DIR}/repos/ecossistema-*; do
        echo "Pulling $(basename ${REPO_DIR})..."
        (cd ${REPO_DIR} && git pull --ff-only)
    done
fi

# 2. Build backend JARs (requires Maven + Java 21)
if [ "$BUILD" = true ]; then
    echo "--- Building backend JARs ---"
    for BACKEND in sgc si wn gpj; do
        BACKEND_DIR="${DEPLOY_DIR}/repos/ecossistema-${BACKEND}-backend"
        echo "Building ${BACKEND}-backend..."
        (cd ${BACKEND_DIR} && mvn package -DskipTests -B -q)
    done
fi

# 3. Docker Compose up
echo "--- Starting Docker Compose (${ENV}) ---"
cd ${COMPOSE_DIR}
docker compose --env-file "${ENV_FILE}" build
docker compose --env-file "${ENV_FILE}" up -d

# 4. Wait for services to be healthy
echo "--- Waiting for services to be healthy ---"
sleep 10
MAX_WAIT=120
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    UNHEALTHY=$(docker compose --env-file "${ENV_FILE}" ps --format json | jq -r 'select(.Health != "healthy" and .Health != "") | .Name' 2>/dev/null | wc -l)
    if [ "$UNHEALTHY" -eq 0 ]; then
        echo "All services healthy!"
        break
    fi
    echo "Waiting... (${ELAPSED}s / ${MAX_WAIT}s)"
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

# 5. Show status
echo "--- Service Status ---"
docker compose --env-file "${ENV_FILE}" ps

echo "=== Deployment of ${ENV} complete ==="
