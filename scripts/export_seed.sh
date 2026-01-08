#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SEED_DIR="$ROOT_DIR/seed"
mkdir -p "$SEED_DIR"

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

if [[ ! -d env ]]; then
  echo "❌ Python virtual environment not found at ./env"
  echo "Create it first: python3 -m venv env && env/bin/pip install -r requirements.txt"
  exit 1
fi

source env/bin/activate

if ! command -v pg_dump >/dev/null 2>&1; then
  echo "❌ pg_dump not found. Install PostgreSQL client tools first."
  exit 1
fi

echo "📦 Exporting database to seed/autodialer_db.dump"
PGPASSWORD="$DB_PASSWORD" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$SEED_DIR/autodialer_db.dump" "$DB_NAME"

echo "📦 Exporting media to seed/media.tar.gz"
if [[ -d media ]]; then
  tar -czf "$SEED_DIR/media.tar.gz" media
else
  echo "⚠️  media/ directory not found; skipping media export"
fi

echo "📦 Exporting Asterisk credentials to seed/asterisk.env"
python manage.py shell -c "from telephony.models import AsteriskServer; s=AsteriskServer.objects.filter(is_active=True).first();\
print('AMI_USERNAME='+ (s.ami_username if s else 'autodialer'));\
print('AMI_PASSWORD='+ (s.ami_password if s else 'amp111'));\
print('AMI_PORT='+ str(s.ami_port if s else 5038));\
print('ARI_USERNAME='+ (s.ari_username if s else 'autodialer'));\
print('ARI_PASSWORD='+ (s.ari_password if s else 'amp111'));\
print('ARI_PORT='+ str(s.ari_port if s else 8088));\
print('ARI_APPLICATION='+ (s.ari_application if s else 'autodialer'));\
print('ARI_HOST='+ (s.ari_host if s else 'localhost'))" > "$SEED_DIR/asterisk.env"

echo "📦 Exporting .env and generated configs"
if [[ -f .env ]]; then
    cp .env "$SEED_DIR/.env.backup"
    echo "  - Copied .env to seed/.env.backup"
fi

if [[ -d docs/generated ]]; then
    tar -czf "$SEED_DIR/configs.tar.gz" -C docs generated
    echo "  - Compressed docs/generated to seed/configs.tar.gz"
fi

echo "✅ Seed export complete"
echo "Copy the 'seed' directory to your target machine."
