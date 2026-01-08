#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f manage.py ]]; then
  echo "❌ Run this from the project root (manage.py not found)."
  exit 1
fi

# Load env vars if present
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

DB_NAME="${DB_NAME:-autodialer_db}"
DB_USER="${DB_USER:-postgres}"
DB_PASSWORD="${DB_PASSWORD:-Shiwansh@123}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"

SEED_DIR="$ROOT_DIR/seed"
DB_DUMP="$SEED_DIR/autodialer_db.dump"
MEDIA_TAR="$SEED_DIR/media.tar.gz"
ASTERISK_ENV="$SEED_DIR/asterisk.env"

if [[ ! -d "$SEED_DIR" ]]; then
  echo "❌ seed/ directory not found."
  echo "Run scripts/export_seed.sh on the source machine and copy seed/ here."
  exit 1
fi

if [[ ! -f "$DB_DUMP" ]]; then
  echo "❌ Database dump not found at $DB_DUMP"
  echo "Run scripts/export_seed.sh on the source machine and copy seed/ here."
  exit 1
fi

if [[ -f "$ASTERISK_ENV" ]]; then
  set -a
  source "$ASTERISK_ENV"
  set +a
fi

AMI_USERNAME="${AMI_USERNAME:-autodialer}"
AMI_PASSWORD="${AMI_PASSWORD:-amp111}"
AMI_PORT="${AMI_PORT:-5038}"
ARI_USERNAME="${ARI_USERNAME:-autodialer}"
ARI_PASSWORD="${ARI_PASSWORD:-amp111}"
ARI_PORT="${ARI_PORT:-8088}"
ARI_APPLICATION="${ARI_APPLICATION:-autodialer}"
ARI_HOST="${ARI_HOST:-localhost}"

if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "⚠️  This script targets Ubuntu. Current OS: ${ID:-unknown}"
  fi
fi

echo "📦 Installing system dependencies (sudo required)"
sudo apt-get update
sudo apt-get install -y \
  python3-venv python3-dev build-essential \
  libpq-dev postgresql postgresql-contrib \
  redis-server \
  unixodbc odbc-postgresql \
  asterisk asterisk-odbc

sudo systemctl enable --now redis-server
sudo systemctl enable --now postgresql
sudo systemctl enable --now asterisk

# Setup Postgres user and database
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';"

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1 || \
  sudo -u postgres psql -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"

# Restore database
echo "📦 Restoring database from seed dump"
PGPASSWORD="$DB_PASSWORD" pg_restore -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -c -d "$DB_NAME" "$DB_DUMP"

# Restore media
if [[ -f "$MEDIA_TAR" ]]; then
  echo "📦 Restoring media files"
  tar -xzf "$MEDIA_TAR" -C "$ROOT_DIR"
fi

# Create virtual environment if missing
if [[ ! -d env ]]; then
  echo "🐍 Creating Python virtualenv"
  python3 -m venv env
fi

source env/bin/activate

# Install Python dependencies
if [[ -f requirements.txt ]]; then
  echo "🐍 Installing Python dependencies"
  pip install --upgrade pip
  pip install -r requirements.txt
fi

# Apply migrations (keeps schema aligned with code)
echo "🧱 Running migrations"
python manage.py migrate

# ODBC configuration
echo "🧩 Configuring ODBC for Asterisk"

sudo tee /etc/odbcinst.ini >/dev/null <<'ODBCINST'
[PostgreSQL Unicode]
Description=PostgreSQL ODBC driver (Unicode)
Driver=/usr/lib/x86_64-linux-gnu/odbc/psqlodbcw.so
Setup=/usr/lib/x86_64-linux-gnu/odbc/libodbcpsqlS.so
UsageCount=1
ODBCINST

sudo tee /etc/odbc.ini >/dev/null <<ODBCINI
[asterisk]
Description=Asterisk Realtime DB
Driver=PostgreSQL Unicode
Servername=${DB_HOST}
Port=${DB_PORT}
Database=${DB_NAME}
Username=${DB_USER}
Password=${DB_PASSWORD}
ReadOnly=No
ODBCINI

# Asterisk realtime configuration
sudo tee /etc/asterisk/res_odbc.conf >/dev/null <<ODBCCONF
[asterisk]
enabled => yes
dsn => asterisk
username => ${DB_USER}
password => ${DB_PASSWORD}
pre-connect => yes
max_connections => 20
ODBCCONF

sudo cp -f docs/generated/sorcery.conf /etc/asterisk/sorcery.conf
sudo cp -f docs/generated/extconfig.conf /etc/asterisk/extconfig.conf
sudo cp -f docs/generated/pjsip_realtime.conf /etc/asterisk/pjsip_realtime.conf

# Deploy generated dialplan + PJSIP custom configs
if [[ -f generated_configs/pjsip_custom.conf ]]; then
  sudo cp -f generated_configs/pjsip_custom.conf /etc/asterisk/pjsip_custom.conf
fi
if [[ -f generated_configs/extensions_custom.conf ]]; then
  sudo cp -f generated_configs/extensions_custom.conf /etc/asterisk/extensions_custom.conf
fi

# Ensure includes in base configs
if ! grep -q "pjsip_realtime.conf" /etc/asterisk/pjsip.conf; then
  echo "#include pjsip_realtime.conf" | sudo tee -a /etc/asterisk/pjsip.conf >/dev/null
fi
if ! grep -q "pjsip_custom.conf" /etc/asterisk/pjsip.conf; then
  echo "#include pjsip_custom.conf" | sudo tee -a /etc/asterisk/pjsip.conf >/dev/null
fi
if ! grep -q "extensions_custom.conf" /etc/asterisk/extensions.conf; then
  echo "#include extensions_custom.conf" | sudo tee -a /etc/asterisk/extensions.conf >/dev/null
fi

# Enable HTTP + ARI + AMI
sudo tee /etc/asterisk/http.conf >/dev/null <<HTTPCONF
[general]
enabled=yes
bindaddr=0.0.0.0
bindport=${ARI_PORT}
HTTPCONF

sudo tee /etc/asterisk/ari.conf >/dev/null <<ARICONF
[general]
enabled = yes
pretty = yes

[${ARI_USERNAME}]
type = user
read_only = no
password = ${ARI_PASSWORD}
ARICONF

sudo tee /etc/asterisk/manager.conf >/dev/null <<AMICONF
[general]
enabled = yes
port = ${AMI_PORT}
bindaddr = 0.0.0.0

[${AMI_USERNAME}]
secret = ${AMI_PASSWORD}
read = all
write = all
AMICONF

sudo asterisk -rx "core reload" || true

# Write a local .env if missing (for DB + redis)
if [[ ! -f .env ]]; then
  cat <<ENVFILE > .env
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
DB_PASSWORD=${DB_PASSWORD}
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
REDIS_URL=redis://127.0.0.1:6379/0
USE_REDIS=1
ENVFILE
fi

echo "✅ Setup complete."
echo "Next: run ./start_autodialer.sh"
