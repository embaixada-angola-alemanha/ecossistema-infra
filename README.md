# Ecossistema Digital — Infraestrutura

[![CI](https://github.com/embaixada-angola-alemanha/ecossistema-infra/actions/workflows/ci.yml/badge.svg)](https://github.com/embaixada-angola-alemanha/ecossistema-infra/actions/workflows/ci.yml)

Infraestrutura Docker Compose para o **Ecossistema Digital** da Embaixada da Republica de Angola na Alemanha. Inclui o ambiente de desenvolvimento local, a stack de deployment para VPS (staging e producao) com Nginx, TLS/Certbot, monitorizacao (Prometheus + Grafana + Loki) e scripts de automacao.

> **Dominio:** `embaixada-angola.site`

## Stack Tecnologica

| Componente | Tecnologia | Versao |
|-----------|------------|--------|
| Base de Dados | PostgreSQL | 16 (Alpine) |
| Cache / Sessoes | Redis | 7 (Alpine) |
| Identity & Access Management | Keycloak | 26 (latest) |
| Object Storage (S3) | MinIO | latest |
| Email Testing | MailHog | latest |
| Message Broker | RabbitMQ | 3 (Management Alpine) |
| Reverse Proxy | Nginx | Alpine |
| Monitorizacao | Prometheus + Grafana + Loki + Promtail | -- |
| Containers | Docker Compose | -- |

## Servicos (Desenvolvimento Local)

| Servico | Imagem | Porta(s) | Descricao |
|---------|--------|----------|-----------|
| **PostgreSQL** | `postgres:16-alpine` | 5432 | Base de dados principal (6 schemas) |
| **Redis** | `redis:7-alpine` | 6379 | Cache e sessoes |
| **Keycloak** | `keycloak:latest` | 8080 | IAM com realm `ecossistema` |
| **MinIO** | `minio/minio:latest` | 9000 (API), 9001 (Console) | Armazenamento de ficheiros |
| **MailHog** | `mailhog/mailhog:latest` | 1025 (SMTP), 8025 (UI) | Teste de emails |
| **RabbitMQ** | `rabbitmq:3-management-alpine` | 5672 (AMQP), 15672 (Management) | Mensageria entre servicos |
| **Nginx** | `nginx:alpine` | 80, 443 | Proxy reverso |

## Quick Start (Desenvolvimento Local)

```bash
# 1. Clonar o repositorio
git clone https://github.com/embaixada-angola-alemanha/ecossistema-infra.git
cd ecossistema-infra

# 2. Copiar ficheiro de ambiente
cp .env.example .env

# 3. Iniciar todos os servicos
./scripts/start.sh

# 4. Verificar que todos os servicos estao saudaveis
./scripts/wait-for-healthy.sh

# 5. Verificar estado
docker compose ps
```

## URLs de Acesso (Local)

| URL | Servico | Credenciais |
|-----|---------|-------------|
| http://localhost | Landing page | -- |
| http://localhost:8080 | Keycloak Admin Console | `admin` / `admin_dev_2026` |
| http://localhost:9001 | MinIO Console | `minio_admin` / `minio_dev_2026` |
| http://localhost:8025 | MailHog UI | -- |
| http://localhost:15672 | RabbitMQ Management | `ecossistema` / via `.env` |

## Bases de Dados

O PostgreSQL contem 6 bases de dados, inicializadas automaticamente via `postgres/init/01-init-databases.sql`:

| Database | Sistema |
|----------|---------|
| `ecossistema_db` | Principal |
| `keycloak_db` | Keycloak IAM |
| `sgc_db` | Sistema de Gestao Consular |
| `si_db` | Site Institucional |
| `wn_db` | WebNoticias |
| `gpj_db` | Gestao de Projectos |

```bash
# Listar bases de dados
docker exec ecossistema-postgres psql -U ecossistema -l

# Conectar a uma BD especifica
docker exec -it ecossistema-postgres psql -U ecossistema -d sgc_db
```

## Keycloak — Realm Ecossistema

O realm `ecossistema` e importado automaticamente a partir de `keycloak/realm-ecossistema.json`.

### Roles

`ADMIN` | `CONSUL` | `OFFICER` | `CITIZEN` | `EDITOR` | `VIEWER`

### Clientes OAuth 2.0

| Client ID | Tipo | Descricao |
|-----------|------|-----------|
| `sgc-frontend` | Public (PKCE) | SGC Frontend SPA |
| `sgc-backend` | Bearer-only | SGC Backend API |
| `si-frontend` | Public (PKCE) | SI Frontend SPA |
| `si-backend` | Bearer-only | SI Backend API |
| `wn-frontend` | Public (PKCE) | WN Frontend SPA |
| `wn-backend` | Bearer-only | WN Backend API |
| `gpj-frontend` | Public (PKCE) | GPJ Frontend SPA |
| `gpj-backend` | Bearer-only | GPJ Backend API |

### Utilizadores de Teste

| Username | Password | Role |
|----------|----------|------|
| `admin` | `admin123` | ADMIN |
| `consul` | `consul123` | CONSUL |
| `officer` | `officer123` | OFFICER |
| `citizen` | `citizen123` | CITIZEN |
| `editor` | `editor123` | EDITOR |
| `viewer` | `viewer123` | VIEWER |

## Nginx — Proxy Reverso

| Path | Destino |
|------|---------|
| `/auth/`, `/realms/`, `/resources/`, `/js/` | Keycloak |
| `/api/sgc/` | `localhost:8081` (SGC Backend) |
| `/api/si/` | `localhost:8082` (SI Backend) |
| `/api/wn/` | `localhost:8083` (WN Backend) |
| `/api/gpj/` | `localhost:8084` (GPJ Backend) |
| `/storage/` | MinIO API |
| `/minio/` | MinIO Console |
| `/mail/` | MailHog UI |
| `/` | Landing page |

## Deployment (Staging & Producao)

O directorio `deploy/` contem toda a configuracao para deployment em VPS (Strato), com separacao de ambientes por gama de portas:

| Ambiente | Portas | Dominio | Env File |
|----------|--------|---------|----------|
| **Staging** | `10xxx` | `stg-*.embaixada-angola.site` | `deploy/.env.staging` |
| **Producao** | `20xxx` | `*.embaixada-angola.site` | `deploy/.env.production` |

### Comandos de Deploy

```bash
# Setup inicial do VPS (Docker, firewall, utilizadores)
./deploy/scripts/setup-vps.sh

# Configurar certificados TLS via Certbot
./deploy/scripts/setup-tls.sh

# Deploy staging
cd deploy && docker compose --env-file .env.staging up -d

# Deploy producao
cd deploy && docker compose --env-file .env.production up -d

# Deploy automatizado (build + deploy)
./deploy/scripts/deploy.sh staging   # ou production

# Backup de bases de dados
./deploy/scripts/backup.sh
```

### Monitorizacao

A stack de monitorizacao e gerida pelo ficheiro `deploy/docker-compose.monitoring.yml`:

- **Prometheus** — metricas de todos os servicos
- **Grafana** — dashboards de visualizacao
- **Loki** — agregacao de logs
- **Promtail** — recolha de logs dos containers

```bash
# Iniciar stack de monitorizacao
cd deploy && docker compose -f docker-compose.monitoring.yml up -d
```

## Migracao WordPress

O directorio `migration/` contem o script de migracao do site WordPress existente para o novo Site Institucional (SI):

```bash
cd migration
pip install -r requirements.txt
python wp_migrate.py
```

O estado da migracao e rastreado em `migration/migration_state.json`.

## Scripts Utilitarios

| Script | Descricao |
|--------|-----------|
| `scripts/start.sh` | Iniciar todos os servicos locais |
| `scripts/stop.sh` | Parar todos os servicos locais |
| `scripts/reset.sh` | Reset completo (apaga todos os dados!) |
| `scripts/wait-for-healthy.sh` | Aguardar que todos os servicos estejam saudaveis |
| `deploy/scripts/setup-vps.sh` | Setup inicial do VPS |
| `deploy/scripts/setup-tls.sh` | Configurar certificados TLS |
| `deploy/scripts/deploy.sh` | Deploy automatizado |
| `deploy/scripts/backup.sh` | Backup de bases de dados |

## Estrutura do Repositorio

```
ecossistema-infra/
├── docker-compose.yml              # Stack de desenvolvimento local
├── .env.example                     # Template de variaveis de ambiente
├── .gitignore
├── README.md
├── keycloak/
│   └── realm-ecossistema.json       # Realm Keycloak (auto-import)
├── nginx/
│   ├── nginx.conf                   # Configuracao principal Nginx
│   └── conf.d/
│       └── default.conf             # Rotas do proxy reverso
├── postgres/
│   └── init/
│       └── 01-init-databases.sql    # Criacao das 6 bases de dados
├── scripts/
│   ├── start.sh
│   ├── stop.sh
│   ├── reset.sh
│   └── wait-for-healthy.sh
├── migration/
│   ├── wp_migrate.py                # Script de migracao WordPress
│   ├── requirements.txt
│   └── migration_state.json
├── deploy/
│   ├── docker-compose.yml           # Stack de staging/producao
│   ├── docker-compose.monitoring.yml
│   ├── .env.staging
│   ├── .env.production
│   ├── init/
│   │   └── 01-init-databases.sql
│   ├── nginx/
│   │   └── sites-available/         # Configuracoes Nginx por dominio
│   ├── monitoring/
│   │   ├── prometheus.yml
│   │   └── promtail.yml
│   └── scripts/
│       ├── setup-vps.sh
│       ├── setup-tls.sh
│       ├── deploy.sh
│       └── backup.sh
└── .github/
    └── workflows/
        └── ci.yml                   # GitHub Actions CI
```

## Requisitos

- Docker 24+
- Docker Compose v2
- Bash (para os scripts)
- Python 3.10+ (apenas para migracao WordPress)

## Projecto Principal

Este repositorio faz parte do [Ecossistema Digital da Embaixada de Angola na Alemanha](https://github.com/embaixada-angola-alemanha/ecossistema-docs).

Consulte o repositorio de documentacao para a visao geral da arquitectura, ADRs, guias de utilizacao e o estado completo do projecto.
