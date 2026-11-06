# Production Deployment Guide — Freelance Agent

Two supported modes, one codebase: **Docker Compose** (recommended) and
**native Linux + systemd**.

---

## 1. Docker Compose

```bash
cp .env.example .env
# REQUIRED edits in .env:
#   FREELANCE_SECRET_KEY     → openssl rand -hex 32
#   FREELANCE_ADMIN_PASSWORD → a strong password
docker compose up -d --build
docker compose logs -f app        # watch startup
```

Startup performs: `alembic upgrade head` → seed (admin user, prompts,
platform rows) → discovery scheduler + outbox worker + Telegram supervisor.

Services: `app` (FastAPI + frontend), `db` (PostgreSQL 16 with volume),
`redis` (optional coordination). Data persists in the `pgdata` volume and
`./backups`.

## 2. Native Linux + systemd

```bash
sudo mkdir -p /opt/freelance-agent
sudo cp -r . /opt/freelance-agent && cd /opt/freelance-agent
sudo ./scripts/setup_linux.sh        # venv + deps + .env + migrations
sudo chown -R www-data:www-data /opt/freelance-agent

# PostgreSQL (if local):
sudo -u postgres psql -c "CREATE USER freelance WITH PASSWORD 'strong-pass';"
sudo -u postgres psql -c "CREATE DATABASE freelance_agent OWNER freelance;"
# then set FREELANCE_DATABASE_URL in .env accordingly

sudo cp systemd/freelance-agent.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now freelance-agent
sudo systemctl status freelance-agent
```

## 3. Environment reference

| Variable | Purpose |
|---|---|
| `FREELANCE_SECRET_KEY` | Signs dashboard tokens + derives credential-encryption key. **Must be random in prod.** |
| `FREELANCE_ENCRYPTION_KEY` | Optional dedicated Fernet key (else derived from secret key) |
| `FREELANCE_DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/freelance_agent` (SQLite only for dev/tests) |
| `FREELANCE_REDIS_URL` | Optional; enables coordination if you scale workers |
| `FREELANCE_ADMIN_USERNAME/PASSWORD` | Seeded on first start |
| `FREELANCE_RATE_LIMIT_PER_MINUTE` | API rate limit per client IP (default 240) |
| `FREELANCE_DEFAULT_SCAN_INTERVAL_MINUTES` | Default discovery interval (overridable per platform) |
| `FREELANCE_DEBUG` | Enables the `demo` testing platform — keep **false** in prod |

## 4. Telegram setup (BotFather)

1. Telegram → **@BotFather** → `/newbot` → choose name/username → copy token.
2. Dashboard → **تلگرام** → paste token → **ذخیره توکن** → **تست اتصال**.
3. Send `/start <pairing code>` from your Telegram account; the chat appears
   in the authorized list.
4. Polling runs automatically. For webhook mode: set `FREELANCE_TELEGRAM_WEBHOOK_SECRET`,
   switch mode to `webhook` in the dashboard, and point BotFather's
   `setWebhook` at `https://your-domain/telegram/webhook/<secret>`.

Tokens are stored encrypted (Fernet) and are never returned by the API
(masked as `••••1234`).

## 5. Backups & restore

```bash
# cron: daily 03:30 backup, 14-day retention
30 3 * * * cd /opt/freelance-agent && ./scripts/backup_db.sh >> backups/backup.log 2>&1

./scripts/restore_db.sh backups/freelance_agent-YYYYMMDD-HHMMSS.dump   # asks for YES
```

## 6. Security checklist

- [ ] Changed `FREELANCE_ADMIN_PASSWORD` and the dashboard password after first login
- [ ] `FREELANCE_SECRET_KEY` is random and backed up (it protects encrypted credentials!)
- [ ] Serving behind HTTPS reverse proxy (nginx/Caddy) when exposed beyond localhost
- [ ] `FREELANCE_DEBUG=false` (demo platform disabled)
- [ ] Only your own chat IDs are authorized in Telegram
- [ ] Firewall: PostgreSQL/Redis not exposed publicly
- [ ] Rate limiting reviewed (`FREELANCE_RATE_LIMIT_PER_MINUTE`)

## 7. Monitoring

- `GET /api/v1/health` (also the Docker healthcheck)
- Dashboard → **لاگ‌های اجرا** (`execution_logs`), per-platform scan logs with
  success/duplicate/filtered counters, AI token usage and estimated cost in
  **تحلیل و آمار**.
- Platform outages: scan failures are recorded on the platform card (last
  error + time) and never crash the scheduler.

## 8. Troubleshooting

| Symptom | Where to look |
|---|---|
| No new projects | Platform enabled? Test connection? Scan logs (duplicates/filtered counters)? |
| Projects stuck "در انتظار تحلیل" | No model assigned for the **analyzer** role, or provider error — see لاگ‌های اجرا |
| Proposal generation blocked | Project must be approved first; max AI attempts reached (edit manually) |
| Submit button error | Price/delivery invalid, duplicate submission, or proposal not ready |
| Telegram silent | Token enabled? Chat paired? `notify_enabled` on? min score too high? |
