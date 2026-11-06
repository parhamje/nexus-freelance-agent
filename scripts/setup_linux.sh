#!/usr/bin/env bash
# Native Linux setup for Freelance Agent (same codebase as Docker mode).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Checking prerequisites"
if ! command -v python3 >/dev/null; then echo "python3 is required"; exit 1; fi
PYV=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
case "$PYV" in 3.12|3.13) ;; *) echo "warning: Python 3.12+ recommended (found $PYV)";; esac
if ! command -v psql >/dev/null; then
  echo "!! PostgreSQL not found. Install it (e.g. apt install postgresql) and create the DB:"
  echo "   sudo -u postgres psql -c \"CREATE USER freelance WITH PASSWORD 'freelance';\""
  echo "   sudo -u postgres psql -c \"CREATE DATABASE freelance_agent OWNER freelance;\""
fi

echo "==> Creating virtualenv (.venv)"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  sed -i "s|FREELANCE_SECRET_KEY=.*|FREELANCE_SECRET_KEY=$SECRET|" .env
  echo "   -> secret key generated"
fi

echo "==> Running migrations"
alembic upgrade head

cat <<'EOF'

Setup complete. Next steps:
  1) Edit .env (database URL, admin password).
  2) Start:  source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
  3) Open:   http://localhost:8000  (login: see FREELANCE_ADMIN_*)
  4) Optional systemd service: see systemd/freelance-agent.service
  5) Backups: scripts/backup_db.sh (add to cron)
EOF
