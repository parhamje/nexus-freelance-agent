"""Connector base class and registry.

Rules every connector must follow:
- Only use publicly accessible endpoints/pages (or APIs the platform documents
  for third parties). Never bypass CAPTCHA, login walls or anti-bot controls.
- Mark a capability `verified=True` only after it has been exercised against
  the live platform.
- Submission is `assisted` unless the platform offers an authorized API.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger
from app.integrations.base.schemas import (AvailabilityCheck, Capabilities,
                                           NormalizedProject, SubmissionPayload,
                                           SubmissionResult)

log = get_logger("connector")

CONNECTORS: dict[str, type["BaseConnector"]] = {}


def register(cls: type["BaseConnector"]) -> type["BaseConnector"]:
    CONNECTORS[cls.slug] = cls
    return cls


class ConnectorError(Exception):
    pass


class PlatformUnavailable(ConnectorError):
    pass


class UnsupportedOperation(ConnectorError):
    pass


class AuthenticationRequired(ConnectorError):
    pass


class BaseConnector(ABC):
    slug: ClassVar[str] = ""
    name: ClassVar[str] = ""
    base_url: ClassVar[str] = ""
    verified: ClassVar[bool] = False

    def __init__(self, credentials: dict | None = None, config: dict | None = None):
        self.credentials = credentials or {}
        self.config = config or {}
        self._client: httpx.AsyncClient | None = None

    # ----------------------------- http helpers ---------------------------- #
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                headers={
                    "User-Agent": settings.user_agent,
                    "Accept-Language": "fa,en;q=0.8",
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                },
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = await self.client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            raise PlatformUnavailable(
                f"{self.name}: HTTP {exc.response.status_code} for {url}"
            ) from exc
        except httpx.HTTPError as exc:
            raise PlatformUnavailable(f"{self.name}: network error for {url}: {exc}") from exc

    async def get_json(self, url: str, **kwargs: Any) -> Any:
        resp = await self.request("GET", url, **kwargs)
        try:
            return resp.json()
        except ValueError as exc:
            raise PlatformUnavailable(f"{self.name}: non-JSON response from {url}") from exc

    async def get_text(self, url: str, **kwargs: Any) -> str:
        return (await self.request("GET", url, **kwargs)).text

    # ---------------------------- capabilities ----------------------------- #
    def capabilities(self) -> Capabilities:
        return Capabilities(verified=self.verified)

    # ------------------------------ operations ----------------------------- #
    @abstractmethod
    async def fetch_projects(self, page: int = 1, max_items: int = 50) -> list[NormalizedProject]:
        """Return the latest projects in normalized form (newest first)."""

    async def fetch_project_details(self, external_id: str, raw: dict | None = None) -> NormalizedProject | None:
        raise UnsupportedOperation(f"{self.name}: project details are not supported")

    async def check_availability(self, external_id: str, raw: dict | None = None) -> AvailabilityCheck:
        return AvailabilityCheck(available=None, reason=f"{self.name}: availability check not supported")

    async def submit_proposal(self, payload: SubmissionPayload) -> SubmissionResult:
        raise UnsupportedOperation(
            f"{self.name}: does not offer a public/authorized proposal API; "
            "use the assisted-submission workflow"
        )

    async def test_connection(self) -> dict:
        try:
            items = await self.fetch_projects(page=1, max_items=1)
            return {"ok": True, "message": f"OK - {len(items)} project(s) readable", "details": {}}
        except ConnectorError as exc:
            return {"ok": False, "message": str(exc), "details": {}}
        finally:
            await self.aclose()

    # ------------------------------ utilities ------------------------------ #
    @staticmethod
    async def polite_delay(seconds: float = 1.0) -> None:
        await asyncio.sleep(seconds)


def ensure_connectors_loaded() -> None:
    """Import every platform module so @register decorators populate CONNECTORS."""
    from app.core.config import settings
    from app.integrations.platforms.karlancer.connector import KarlancerConnector  # noqa: F401
    from app.integrations.platforms.ponisha.connector import PonishaConnector  # noqa: F401
    from app.integrations.platforms.parscoders.connector import ParsCodersConnector  # noqa: F401
    if settings.debug:
        from app.integrations.platforms.demo_connector import DemoConnector  # noqa: F401


def get_connector(slug: str, credentials: dict | None = None,
                  config: dict | None = None) -> BaseConnector:
    """Instantiate a connector by slug."""
    ensure_connectors_loaded()
    if slug not in CONNECTORS:
        raise ConnectorError(f"Unknown platform connector: {slug}")
    return CONNECTORS[slug](credentials=credentials, config=config)
