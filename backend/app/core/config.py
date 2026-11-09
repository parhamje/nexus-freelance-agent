"""Application configuration (pydantic-settings, env + .env)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent.parent  # backend/app
BACKEND_DIR = APP_DIR.parent                       # backend
PROJECT_DIR = BACKEND_DIR.parent                   # repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FREELANCE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Freelance Agent"
    app_version: str = "1.0.0"
    debug: bool = False

    secret_key: str = "change-me-to-a-long-random-string"
    encryption_key: str = ""

    database_url: str = "postgresql+asyncpg://freelance:freelance@localhost:5432/freelance_agent"
    redis_url: str = ""

    admin_username: str = "admin"
    admin_password: str = "change-me-please"
    seed_admin: bool = False

    access_token_expire_minutes: int = 60 * 24
    rate_limit_per_minute: int = 1200

    default_scan_interval_minutes: int = 20
    time_saved_per_proposal_minutes: int = 45

    frontend_dir: str = str(PROJECT_DIR / "frontend")
    log_level: str = "INFO"

    telegram_webhook_secret: str = ""
    telegram_proxy: str = ""

    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36 FreelanceAgent/1.0 (+personal assistant; respects robots.txt)"
    )

    @property
    def frontend_path(self) -> Path:
        p = Path(self.frontend_dir)
        if p.is_absolute():
            return p
        if (PROJECT_DIR / p).exists():
            return (PROJECT_DIR / p).resolve()
        if (BACKEND_DIR / p).exists():
            return (BACKEND_DIR / p).resolve()
        return (PROJECT_DIR / p).resolve()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
