# ⚡ NEXUS — Autonomous Freelance Intelligence Suite

**سامانه جامع پایش هوشمند مناقصات و پیشنهاددهی خودکار فریلنسری — با کنترل کامل انسانی**

An AI-powered freelance opportunity discovery and proposal assistant. It watches
Iranian freelance platforms, analyzes new projects against your *verified*
developer profile, notifies you (Web + Telegram), and drafts Persian proposals —
**only after you approve a project** — and never submits anything without a
second, explicit approval.

```
DISCOVER → ANALYZE → NOTIFY → OWNER APPROVES PROJECT → GENERATE PROPOSAL
        → QUALITY REVIEW → OWNER APPROVES PROPOSAL → SUBMIT (or assisted)
```

## Key guarantees

| Rule | How it is enforced |
|---|---|
| No proposal without project approval | `generate_for_project()` rejects any project not in `approved_for_proposal`/`proposal_ready` |
| No submission without final approval | Submission only starts from the explicit **تأیید و ارسال** action (`POST /proposals/{id}/submit`) |
| No fake success | Assisted submissions stay `assisted_pending` until *you* confirm; API submissions store the real result |
| No invented facts | AI prompts forbid fabricating experience/bids/ratings; analysis uses only your developer profile + platform data |
| Duplicate safety | external-ID + canonical-URL + content-hash + title-similarity dedup, plus unique DB constraints |
| Secret safety | Fernet-encrypted credentials, masked in every API response, HMAC-signed dashboard tokens, rate limiting |

## Architecture (modular monolith)

```
backend/app/
├── core/          config, async SQLAlchemy, security (Fernet/scrypt/HMAC), seeds
├── models.py      21 tables (projects, analyses, proposals, versions, submissions,
│                  platforms, credentials, scan logs, ai_providers, agent config,
│                  prompts+versions, notifications, outbox, logs, profile, telegram…)
├── integrations/
│   ├── base/      connector ABC + capability flags + normalized schemas
│   └── platforms/ karlancer | ponisha | parscoders | demo (debug only)
├── services/      discovery scheduler, outbox worker, analyzer, proposals,
│                  submissions, notifications, analytics, text utils
├── ai/            provider manager (OpenAI-compatible / Anthropic / Ollama) + Persian agents
├── api/routes/    auth, projects, proposals, platforms, ai, profile, telegram,
│                  notifications, misc (analytics/logs/health/WebSocket)
└── telegram/      aiogram 3 bot (Persian, pairing-code, full workflow buttons)

frontend/          vanilla JS ES6+ SPA (Tailwind CDN, Vazirmatn, RTL/LTR, dark/light,
                   original synthesized notification chime via WebAudio)
alembic/           async migrations (0001 = full schema from ORM metadata)
```

Background work (discovery scheduler, outbox worker, Telegram supervisor) runs
inside the same process, independently of any open browser tab, and survives
restarts through the transactional **outbox** (`outbox_events` + retry/backoff).

## Quick start

### A. Docker Compose (production)

```bash
cp .env.example .env       # set FREELANCE_SECRET_KEY + FREELANCE_ADMIN_PASSWORD
docker compose up -d --build
# → http://localhost:8000
```

### B. Native Linux (same codebase)

```bash
./scripts/setup_linux.sh          # venv, deps, .env, migrations
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
```

First login: `admin` / the password in `.env` (**change it** in Settings).

## Platform integration status (verified 2026-11-04)

Honesty matrix — capabilities are declared per connector and surfaced in the UI:

| Platform | Discovery method | Verified live | Proposal submission |
|---|---|---|---|
| **Karlancer** | Platform's own public search API `karlancer.com/api/publics/search/projects` (no auth, same endpoint the website calls) | ✅ HTTP 200, fields parsed | ❌ no public API → **assisted** |
| **Ponisha** | Public SSR page `ponisha.ir/search/projects` (`__NEXT_DATA__` JSON) | ✅ full project objects parsed | ❌ → **assisted** |
| **ParsCoders** | Public sitemap `parscoders.com/sitemap/project.xml` + public project pages (robots.txt respected; `/api/` is disallowed and never touched) | ✅ sitemap + detail pages parsed | ❌ → **assisted** |

- New connectors: subclass `BaseConnector`, set capability flags, register with
  `@register` — a disabled platform row appears automatically in the dashboard.
- No connector bypasses CAPTCHA, login walls, or anti-bot protections.
- **Assisted submission**: the app prepares text + price + delivery, opens the
  original project URL, and you post it yourself — then confirm, which is the
  only moment a `submitted` record is created.

## Configuration highlights

- **Agent Configuration** page: global/per-platform scan intervals, max items
  per scan, include/exclude keywords, budget and category filters,
  recommendation threshold (default **70**), quality threshold (**75**),
  max generation attempts (**2**).
- **AI Providers**: any OpenAI-compatible endpoint, Anthropic, or local Ollama;
  independent model selection for analyzer / proposal generator / quality
  reviewer / copilot; optional per-1k-token cost rates for cost estimates.
- **Prompt Studio**: the Persian system prompts of all agents, versioned.
- **Developer Profile**: your verified skills (1–5 levels), experience, links,
  minimum budget — the single source of truth the AI is allowed to use.

## Telegram

1. Create a bot with @BotFather, paste the token in the **تلگرام** page.
2. Send `/start <pairing-code>` from your chat (code shown on the page).
3. You get Persian notifications with inline buttons: تأیید/رد پروژه, تولید
   پیشنهاد, ویرایش, تولید مجدد, تأیید و ارسال, تأیید ارسال دستی.

## Operations

- Backups: `scripts/backup_db.sh` (cron example in docs/DEPLOYMENT.md), restore: `scripts/restore_db.sh`
- Migrations: `alembic upgrade head` (runs automatically in Docker)
- Health: `GET /api/v1/health`, API docs at `/api/docs`
- Logs: dashboard **لاگ‌های اجرا** page (also `execution_logs` table)

## Testing

```bash
pip install pytest pytest-asyncio
pytest tests/
```

The suite covers dedup logic, token/URL utilities, credential encryption,
connector normalization (offline fixtures) and an API smoke test. The `demo`
platform (enabled only when `FREELANCE_DEBUG=true`) lets you exercise the full
pipeline end-to-end without touching real platforms.

## Honest limitations

- No platform offers an official public developer API today, so **no connector
  submits proposals programmatically** — all three use the assisted workflow.
- Availability checks are best-effort (e.g. Ponisha `bidding_closed_at`,
  Karlancer `is_expired`); ParsCoders reports `unknown` when no explicit
  closed marker is on the page. Always glance at the project page before paying.
- AI output quality depends on the configured model; the quality reviewer warns
  but cannot guarantee outcomes.
