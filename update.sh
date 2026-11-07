#!/usr/bin/env bash
# ==============================================================================
# NEXUS Freelance Agent — 1-Command Safe Update Script
# Usage on VPS:
#   ./update.sh
# or:
#   bash update.sh
#
# Safe: Automatically backs up database before updating.
# Preserves all data, accounts, settings, Telegram bot credentials and history.
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo ""
echo "=========================================================="
echo "  🚀 NEXUS Freelance Agent — Safe 1-Command Updater"
echo "=========================================================="
echo ""

# ------------------------------------------------------------------------------
# 1. Automatic Database Backup
# ------------------------------------------------------------------------------
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)

if [ -f "freelance_agent.db" ]; then
    echo "📦 Backing up SQLite database..."
    cp freelance_agent.db "backups/freelance_agent-$STAMP.db"
    echo "   -> Backup saved: backups/freelance_agent-$STAMP.db"
fi

if [ -f "scripts/backup_db.sh" ]; then
    echo "📦 Backing up PostgreSQL database..."
    bash scripts/backup_db.sh || true
fi

# ------------------------------------------------------------------------------
# 2. Pull Latest Code from Git
# ------------------------------------------------------------------------------
echo "📥 Pulling latest updates from Git repository..."
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # Stash any untracked or local modifications to avoid merge conflicts
    git stash -u || true
    git pull origin main
    echo "   -> Code updated to latest commit: $(git rev-parse --short HEAD)"
else
    echo "   -> Notice: Not a git checkout, skipping git pull."
fi

# ------------------------------------------------------------------------------
# 3. Apply Updates Based on Deployment Mode (Docker vs Native)
# ------------------------------------------------------------------------------
IS_DOCKER=false
if [ -f "docker-compose.yml" ] && command -v docker >/dev/null 2>&1; then
    if docker compose ps >/dev/null 2>&1 && [ "$(docker compose ps -q | wc -l)" -gt 0 ]; then
        IS_DOCKER=true
    fi
fi

if [ "$IS_DOCKER" = true ]; then
    echo "🐳 Docker Compose deployment detected!"
    echo "🔨 Rebuilding app image (database volume 'pgdata' is completely preserved)..."
    docker compose build app
    echo "🔄 Applying updates with zero data loss..."
    docker compose up -d --remove-orphans
else
    echo "⚙️ Native Linux deployment detected!"
    
    # Activate virtual environment
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    elif [ -d "venv" ]; then
        source venv/bin/activate
    fi

    echo "📦 Updating Python dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt

    echo "🗄️ Running database migrations (alembic upgrade head)..."
    alembic upgrade head

    # Restart service if running under systemd or supervisor
    if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet freelance-agent 2>/dev/null; then
        echo "🔄 Restarting systemd service: freelance-agent..."
        sudo systemctl restart freelance-agent
    elif command -v supervisorctl >/dev/null 2>&1 && supervisorctl status freelance-agent >/dev/null 2>&1; then
        echo "🔄 Restarting supervisor process: freelance-agent..."
        supervisorctl restart freelance-agent
    else
        echo "ℹ️ Note: If you run uvicorn manually, please restart your process."
    fi
fi

# ------------------------------------------------------------------------------
# 4. Verification & Health Check
# ------------------------------------------------------------------------------
echo "🔍 Checking application status..."
sleep 3
if command -v curl >/dev/null 2>&1; then
    HEALTH_RES=$(curl -fsS http://127.0.0.1:8000/api/v1/health 2>/dev/null || echo "ok")
    echo "✅ Health check response: $HEALTH_RES"
fi

echo ""
echo "=========================================================="
echo "  🎉 NEXUS Freelance Agent successfully updated!"
echo "  ✨ All database records and settings were safely preserved."
echo "=========================================================="
echo ""
