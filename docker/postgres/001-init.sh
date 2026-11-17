#!/bin/sh
# Sourced by the Postgres entrypoint only on an empty data directory.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password APP_DB_PASSWORD
CREATE EXTENSION IF NOT EXISTS vector;
CREATE ROLE sdlc_app LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"DBNAME" TO sdlc_app;
GRANT USAGE ON SCHEMA public TO sdlc_app;
SQL
