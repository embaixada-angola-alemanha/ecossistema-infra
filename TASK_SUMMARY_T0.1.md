# Task Execution Summary — T0.1

| Field | Value |
|-------|-------|
| **Task ID** | T0.1 |
| **Name** | Docker Compose + Infra Repo |
| **Sprint** | S0 — Infraestrutura & Fundacao |
| **Repo** | ecossistema-infra |
| **Planned Hours** | 12h |
| **Date** | 2026-02-16 |
| **Status** | DONE |

---

## Objective

Create the `ecossistema-infra` repository with all local development infrastructure services via Docker Compose — the foundation every other system (GPJ, SGC, SI, WN) depends on.

## Deliverables

### Files Created (12 files, 999+ lines)

| File | Purpose |
|------|---------|
| `docker-compose.yml` | 6 services with healthchecks, volumes, networks |
| `.env.example` | Environment template with all credentials |
| `.env` | Local dev environment (gitignored) |
| `.gitignore` | Ignores .env, data/, IDE files |
| `postgres/init/01-init-databases.sql` | Creates 6 databases |
| `keycloak/realm-ecossistema.json` | Realm, 6 roles, 8 clients, 6 test users |
| `nginx/nginx.conf` | Main nginx config |
| `nginx/conf.d/default.conf` | Reverse proxy rules + landing page |
| `scripts/start.sh` | Start all services + wait for healthy |
| `scripts/stop.sh` | Graceful shutdown |
| `scripts/reset.sh` | Destroy all data (with confirmation) |
| `scripts/wait-for-healthy.sh` | Poll until all services are healthy |
| `README.md` | Full documentation |

### Services Deployed

| Service | Image | Port(s) | Status |
|---------|-------|---------|--------|
| PostgreSQL | postgres:16-alpine | 5432 | Healthy |
| Redis | redis:7-alpine | 6379 | Healthy |
| Keycloak | keycloak:latest | 8080 | Healthy |
| MinIO | minio/minio:latest | 9000, 9001 | Healthy |
| MailHog | mailhog/mailhog:latest | 1025, 8025 | Healthy |
| Nginx | nginx:alpine | 80, 443 | Healthy |

### PostgreSQL Databases

`ecossistema_db`, `keycloak_db`, `sgc_db`, `si_db`, `wn_db`, `gpj_db`

### Keycloak Realm: `ecossistema`

- **Locales:** pt, de, en, cs
- **Roles:** ADMIN, CONSUL, OFFICER, CITIZEN, EDITOR, VIEWER
- **Clients:** 8 (sgc/si/wn/gpj — frontend PKCE + backend bearer-only)
- **Test Users:** 6 (one per role, simple passwords)
- **SMTP:** Configured to MailHog

## Issues & Fixes

| # | Issue | Root Cause | Fix |
|---|-------|------------|-----|
| 1 | Keycloak healthcheck failed | Keycloak 26.x serves `/health/ready` on management port 9000, not 8080 | Changed healthcheck to target port 9000; increased `start_period` to 45s |
| 2 | Nginx reported unhealthy | Alpine resolves `localhost` to IPv6 `::1` first, but nginx listens on IPv4 | Changed healthcheck to use `127.0.0.1` instead of `localhost` |

## Verification Checklist

- [x] `docker compose up -d` starts all services without errors
- [x] `docker compose ps` shows all 6 services as healthy
- [x] Keycloak admin login works (admin / admin_dev_2026)
- [x] Keycloak `ecossistema` realm imported with roles, clients, users
- [x] Nginx landing page accessible at http://localhost
- [x] MinIO Console accessible at http://localhost:9001
- [x] MailHog UI accessible at http://localhost:8025
- [x] PostgreSQL lists all 6 databases
- [x] Redis responds with PONG

## Git Commits

| Hash | Message |
|------|---------|
| `39f2a9f` | T0.1: Docker Compose + local dev infrastructure |
| `ec821d4` | fix: Keycloak healthcheck uses management port 9000 |
| `c8b4e6c` | fix: nginx healthcheck uses 127.0.0.1 instead of localhost |

## Next Task

**T0.2 — Commons Maven Multi-Module** (12h, Sprint 0)
