"""Pydantic schemas shared by all platform connectors."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedProject(BaseModel):
    """Platform-independent project representation produced by every connector."""
    external_id: str
    title: str
    description: str = ""
    url: str
    budget_min: float | None = None
    budget_max: float | None = None
    currency: str = "IRT"  # Iranian Toman
    deadline: datetime | None = None
    published_at: datetime | None = None
    client_name: str | None = None
    client_info: dict[str, Any] = Field(default_factory=dict)
    category: str | None = None
    skills: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class SubmissionPayload(BaseModel):
    external_id: str
    url: str
    title: str
    content: str
    price: float | None = None
    currency: str = "IRT"
    delivery_days: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SubmissionResult(BaseModel):
    success: bool
    method: Literal["api", "assisted"] = "assisted"
    external_submission_id: str | None = None
    message: str = ""
    raw: dict[str, Any] = Field(default_factory=dict)


class Capabilities(BaseModel):
    """What a platform connector can actually do. `verified` is only set True
    after the method has been exercised against the live platform."""
    fetch_projects: bool = True
    fetch_details: bool = True
    check_availability: bool = True
    submit_proposal: bool = False
    submit_method: Literal["none", "api", "assisted"] = "none"
    requires_credentials: bool = False
    authenticated: bool = False
    verified: bool = False
    notes: str = ""


class AvailabilityCheck(BaseModel):
    available: bool | None = None   # None = cannot determine
    reason: str = ""
