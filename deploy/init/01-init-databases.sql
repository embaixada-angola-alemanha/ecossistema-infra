-- =============================================================================
-- Ecossistema Digital — Database Initialization
-- Creates all project databases using the default superuser (ecossistema)
-- =============================================================================

-- Keycloak identity management
CREATE DATABASE keycloak_db;

-- SGC — Sistema de Gestao Consular
CREATE DATABASE sgc_db;

-- SI — Site Institucional
CREATE DATABASE si_db;

-- WN — WebNoticias
CREATE DATABASE wn_db;

-- GPJ — Gestao de Projetos
CREATE DATABASE gpj_db;

-- Note: ecossistema_db is created automatically via POSTGRES_DB env var

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE keycloak_db TO ecossistema;
GRANT ALL PRIVILEGES ON DATABASE sgc_db TO ecossistema;
GRANT ALL PRIVILEGES ON DATABASE si_db TO ecossistema;
GRANT ALL PRIVILEGES ON DATABASE wn_db TO ecossistema;
GRANT ALL PRIVILEGES ON DATABASE gpj_db TO ecossistema;
