#!/usr/bin/env bash
# PostgreSQL backup (custom format). Works inside Docker too.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${FREELANCE_BACKUP_DIR:-./backups}"
RETENTION_DAYS="${FREELANCE_BACKUP_RETENTION:-14}"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

if [ -f .env ]; then set -a; source .env; set +a; fi
PGUSER="${POSTGRES_USER:-freelance}"
PGPASS="${POSTGRES_PASSWORD:-freelance}"
PGDB="${POSTGRES_DB:-freelance_agent}"
PGHOST="${POSTGRES_HOST:-localhost}"
PGPORT="${POSTGRES_PORT:-5432}"

# Inside docker-compose network? use the db container
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q freelance-agent-db-1; then
  docker exec freelance-agent-db-1 pg_dump -U "$PGUSER" -Fc "$PGDB" > "$BACKUP_DIR/freelance_agent-$STAMP.dump"
else
  PGPASSWORD="$PGPASS" pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -Fc "$PGDB" > "$BACKUP_DIR/freelance_agent-$STAMP.dump"
fi

echo "backup written: $BACKUP_DIR/freelance_agent-$STAMP.dump"
find "$BACKUP_DIR" -name 'freelance_agent-*.dump' -mtime +"$RETENTION_DAYS" -delete
echo "retention: kept last $RETENTION_DAYS days"
