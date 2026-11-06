"""Test configuration: isolate env BEFORE any app import."""
import os
import sys
import tempfile

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, _BACKEND)

_TMP = tempfile.mkdtemp(prefix="fa_test_")
_DB_PATH = os.path.join(_TMP, "fa_test.db")
os.environ["FREELANCE_DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ["FREELANCE_DEBUG"] = "true"
os.environ["FREELANCE_SECRET_KEY"] = "test-secret-key-for-pytest"
os.environ["FREELANCE_ADMIN_USERNAME"] = "admin"
os.environ["FREELANCE_ADMIN_PASSWORD"] = "change-me-please"
os.environ["FREELANCE_LOG_LEVEL"] = "WARNING"


def fresh_db():
    """Dispose the cached engine and delete the SQLite file for a clean slate."""
    import asyncio

    async def _dispose():
        from app.core.db import dispose_engine

        await dispose_engine()

    asyncio.run(_dispose())
    if os.path.exists(_DB_PATH):
        os.unlink(_DB_PATH)
