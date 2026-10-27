#!/bin/bash
set -euo pipefail
# The API role owns its database but is not the PostgreSQL superuser.
export BG_APP_PASSWORD="$(cat /run/secrets/db_password)"
psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<'SQL'
\getenv app_password BG_APP_PASSWORD
CREATE ROLE bakagateway LOGIN PASSWORD :'app_password' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE DATABASE bakagateway OWNER bakagateway;
SQL
unset BG_APP_PASSWORD
