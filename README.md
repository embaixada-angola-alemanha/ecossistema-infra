# Ecossistema Digital — Infraestrutura

Infraestrutura de desenvolvimento local para o Ecossistema Digital da Embaixada de Angola na Alemanha.

## Serviços

| Serviço | Imagem | Porta(s) | Descrição |
|---------|--------|----------|-----------|
| **PostgreSQL** | postgres:16-alpine | 5432 | Base de dados principal |
| **Redis** | redis:7-alpine | 6379 | Cache e sessões |
| **Keycloak** | keycloak:latest | 8080 | Identity & Access Management |
| **MinIO** | minio/minio:latest | 9000, 9001 | Object Storage (S3-compatible) |
| **MailHog** | mailhog/mailhog:latest | 1025 (SMTP), 8025 (UI) | Email testing |
| **Nginx** | nginx:alpine | 80, 443 | Reverse proxy |

## Quick Start

```bash
# 1. Copiar ficheiro de ambiente
cp .env.example .env

# 2. Iniciar todos os serviços
./scripts/start.sh

# 3. Verificar estado
docker compose ps
```

## URLs de Acesso

| URL | Serviço | Credenciais |
|-----|---------|-------------|
| http://localhost | Landing page | — |
| http://localhost:8080 | Keycloak Admin | admin / admin_dev_2026 |
| http://localhost:9001 | MinIO Console | minio_admin / minio_dev_2026 |
| http://localhost:8025 | MailHog UI | — |

## Bases de Dados

PostgreSQL contém 6 bases de dados:

| Database | Sistema |
|----------|---------|
| `ecossistema_db` | Principal |
| `keycloak_db` | Keycloak IAM |
| `sgc_db` | Sistema de Gestão Consular |
| `si_db` | Site Institucional |
| `wn_db` | WebNotícias |
| `gpj_db` | Gestão de Projetos |

```bash
# Listar bases de dados
docker exec ecossistema-postgres psql -U ecossistema -l

# Conectar a uma BD específica
docker exec -it ecossistema-postgres psql -U ecossistema -d gpj_db
```

## Keycloak — Realm Ecossistema

**Realm:** `ecossistema`

### Roles

ADMIN, CONSUL, OFFICER, CITIZEN, EDITOR, VIEWER

### Clientes

| Client ID | Tipo | Descrição |
|-----------|------|-----------|
| sgc-frontend | Public (PKCE) | SGC Frontend SPA |
| sgc-backend | Bearer-only | SGC Backend API |
| si-frontend | Public (PKCE) | SI Frontend SPA |
| si-backend | Bearer-only | SI Backend API |
| wn-frontend | Public (PKCE) | WN Frontend SPA |
| wn-backend | Bearer-only | WN Backend API |
| gpj-frontend | Public (PKCE) | GPJ Frontend SPA |
| gpj-backend | Bearer-only | GPJ Backend API |

### Utilizadores de Teste

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | ADMIN |
| consul | consul123 | CONSUL |
| officer | officer123 | OFFICER |
| citizen | citizen123 | CITIZEN |
| editor | editor123 | EDITOR |
| viewer | viewer123 | VIEWER |

## Nginx — Proxy Reverso

| Path | Destino |
|------|---------|
| `/auth/`, `/realms/`, `/resources/`, `/js/` | Keycloak |
| `/api/sgc/` | localhost:8081 (SGC Backend) |
| `/api/si/` | localhost:8082 (SI Backend) |
| `/api/wn/` | localhost:8083 (WN Backend) |
| `/api/gpj/` | localhost:8084 (GPJ Backend) |
| `/storage/` | MinIO API |
| `/minio/` | MinIO Console |
| `/mail/` | MailHog UI |
| `/` | Landing page |

## Comandos

```bash
# Iniciar
./scripts/start.sh

# Parar
./scripts/stop.sh

# Reset completo (apaga todos os dados!)
./scripts/reset.sh

# Verificar saúde dos serviços
./scripts/wait-for-healthy.sh

# Logs de um serviço
docker compose logs -f keycloak

# Redis CLI
docker exec ecossistema-redis redis-cli -a redis_dev_2026 ping
```

## Estrutura

```
ecossistema-infra/
├── docker-compose.yml
├── .env / .env.example
├── .gitignore
├── README.md
├── keycloak/
│   └── realm-ecossistema.json
├── nginx/
│   ├── nginx.conf
│   └── conf.d/default.conf
├── postgres/
│   └── init/01-init-databases.sql
└── scripts/
    ├── start.sh
    ├── stop.sh
    ├── reset.sh
    └── wait-for-healthy.sh
```
