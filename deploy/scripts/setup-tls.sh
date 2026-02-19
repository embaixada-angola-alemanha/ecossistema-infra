#!/bin/bash
# =============================================================================
# Ecossistema Digital — TLS Certificate Setup
# Requires: certbot, python3-certbot-nginx
# Usage: sudo ./setup-tls.sh
# =============================================================================

set -euo pipefail
DOMAIN="embaixada-angola.site"
EMAIL="admin@${DOMAIN}"

echo "=== Setting up TLS for ${DOMAIN} ==="

# Install certbot if not present
if ! command -v certbot &> /dev/null; then
    apt-get update
    apt-get install -y certbot python3-certbot-nginx
fi

# Get wildcard certificate (requires DNS challenge)
# Option 1: Wildcard (manual DNS verification)
# certbot certonly --manual --preferred-challenges dns -d "*.${DOMAIN}" -d "${DOMAIN}" --email "${EMAIL}" --agree-tos

# Option 2: Individual certs via Nginx plugin (automated)
certbot --nginx -d "${DOMAIN}" \
  -d "sgc.${DOMAIN}" -d "si.${DOMAIN}" -d "wn.${DOMAIN}" -d "gpj.${DOMAIN}" \
  -d "api-sgc.${DOMAIN}" -d "api-si.${DOMAIN}" -d "api-wn.${DOMAIN}" -d "api-gpj.${DOMAIN}" \
  -d "auth.${DOMAIN}" -d "grafana.${DOMAIN}" \
  -d "stg-sgc.${DOMAIN}" -d "stg-si.${DOMAIN}" -d "stg-wn.${DOMAIN}" -d "stg-gpj.${DOMAIN}" \
  -d "stg-api-sgc.${DOMAIN}" -d "stg-api-si.${DOMAIN}" -d "stg-api-wn.${DOMAIN}" -d "stg-api-gpj.${DOMAIN}" \
  -d "stg-auth.${DOMAIN}" -d "stg-grafana.${DOMAIN}" \
  --email "${EMAIL}" --agree-tos --no-eff-email

# Setup auto-renewal
systemctl enable certbot.timer
systemctl start certbot.timer

echo "=== TLS setup complete ==="
echo "Certificates will auto-renew via certbot timer"
