#!/bin/sh
# Add a separate Windmill database on the existing PostgreSQL cluster.
# Run on every startup through a one-shot admin service, including old volumes.
set -eu
test "$WINDMILL_DB_PASSWORD" != "$PGPASSWORD"
test "$WINDMILL_DB_PASSWORD" != "$APP_DB_PASSWORD"
psql -v ON_ERROR_STOP=1 <<'SQL'
SELECT pg_advisory_lock(6006001);
SELECT 'CREATE ROLE windmill_user' WHERE NOT EXISTS
  (SELECT FROM pg_roles WHERE rolname='windmill_user') \gexec
SELECT 'CREATE ROLE windmill_admin BYPASSRLS' WHERE NOT EXISTS
  (SELECT FROM pg_roles WHERE rolname='windmill_admin') \gexec
GRANT windmill_user TO windmill_admin;
\getenv wm_password WINDMILL_DB_PASSWORD
SELECT format('CREATE ROLE windmill_login LOGIN PASSWORD %L', :'wm_password')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname='windmill_login') \gexec
GRANT windmill_admin, windmill_user TO windmill_login;
SELECT 'CREATE DATABASE windmill OWNER windmill_login' WHERE NOT EXISTS
  (SELECT FROM pg_database WHERE datname='windmill') \gexec
REVOKE CONNECT ON DATABASE :"DBNAME" FROM PUBLIC;
GRANT CONNECT ON DATABASE :"DBNAME" TO sdlc_app;
REVOKE CONNECT ON DATABASE windmill FROM PUBLIC;
GRANT CONNECT ON DATABASE windmill TO windmill_login;
SELECT pg_advisory_unlock(6006001);
\connect windmill
GRANT USAGE ON SCHEMA public TO windmill_user, windmill_admin;
SQL
