#!/usr/bin/env bash
# Restore a backup created by backup_db.sh
set -euo pipefail
cd "$(dirname "$0")/.."

FILE="${1:?usage: restore_db.sh <backup.dump>}"
if [ -f .env ]; then set -a; source .env; set +a; fi
PGUSER="${POSTGRES_USER:-freelance}"
PGPASS="${POSTGRES_PASSWORD:-freelance}"
PGDB="${POSTGRES_DB:-freelance_agent}"
PGHOST="${POSTGRES_HOST:-localhost}"

read -rp "Restore $FILE into database '$PGDB'? Existing data will be REPLACED. Type YES to continue: " ok
[ "$ok" = "YES" ] || { echo "aborted"; exit 1; }

PGPASSWORD="$PGPASS" pg_restore -h "$PGHOST" -U "$PGUSER" -d "$PGDB" --clean --if-exists "$FILE"
echo "restore complete"
