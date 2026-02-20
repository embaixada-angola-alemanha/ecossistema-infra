#!/bin/bash
# =============================================================================
# Ecossistema Digital — Initial VPS Provisioning
# Run as root on a fresh Ubuntu 22.04/24.04 VPS
# =============================================================================

set -euo pipefail

DEPLOY_USER="ecossistema"
DEPLOY_DIR="/opt/ecossistema"
BACKUP_DIR="/opt/ecossistema/backups"

echo "=== Ecossistema Digital — VPS Setup ==="

# 1. System updates
apt-get update && apt-get upgrade -y

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker ${DEPLOY_USER} || true

# 3. Install Docker Compose plugin
apt-get install -y docker-compose-plugin

# 4. Install Nginx
apt-get install -y nginx

# 5. Install Certbot
apt-get install -y certbot python3-certbot-nginx

# 6. Install Java 21 + Maven (needed for backend builds)
apt-get install -y temurin-21-jdk || {
    wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public | gpg --dearmor -o /etc/apt/keyrings/adoptium.gpg
    echo "deb [signed-by=/etc/apt/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb $(lsb_release -cs) main" > /etc/apt/sources.list.d/adoptium.list
    apt-get update && apt-get install -y temurin-21-jdk
}
apt-get install -y maven

# 7. Install other tools
apt-get install -y git ufw htop curl wget unzip jq postgresql-client

# 8. Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable

# 9. Create deployment user and directories
id ${DEPLOY_USER} &>/dev/null || useradd -m -s /bin/bash ${DEPLOY_USER}
usermod -aG docker ${DEPLOY_USER}
mkdir -p ${DEPLOY_DIR}/{repos,logs,backups,scripts}
chown -R ${DEPLOY_USER}:${DEPLOY_USER} ${DEPLOY_DIR}

# 10. Clone repositories
su - ${DEPLOY_USER} -c "
cd ${DEPLOY_DIR}/repos
for REPO in ecossistema-infra ecossistema-sgc-backend ecossistema-si-backend ecossistema-wn-backend ecossistema-gpj-backend ecossistema-sgc-frontend ecossistema-si-frontend ecossistema-wn-frontend ecossistema-gpj-frontend; do
    if [ ! -d \${REPO} ]; then
        git clone https://github.com/embaixada-angola-alemanha/\${REPO}.git
    fi
done
"

# 11. Setup Nginx configs
ln -sf ${DEPLOY_DIR}/repos/ecossistema-infra/deploy/nginx/sites-available/embaixada-prod.conf /etc/nginx/sites-enabled/
ln -sf ${DEPLOY_DIR}/repos/ecossistema-infra/deploy/nginx/sites-available/embaixada-staging.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# 12. Setup backup cron
cp ${DEPLOY_DIR}/repos/ecossistema-infra/deploy/scripts/backup.sh ${DEPLOY_DIR}/scripts/
chmod +x ${DEPLOY_DIR}/scripts/backup.sh
echo "0 2 * * * ${DEPLOY_USER} ${DEPLOY_DIR}/scripts/backup.sh >> ${DEPLOY_DIR}/logs/backup.log 2>&1" > /etc/cron.d/ecossistema-backup

echo "=== VPS Setup Complete ==="
echo "Next steps:"
echo "  1. Run setup-tls.sh to configure TLS certificates"
echo "  2. Copy .env.staging and .env.production with real credentials"
echo "  3. Run deploy.sh staging to deploy staging"
echo "  4. Run deploy.sh production to deploy production"
