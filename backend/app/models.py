"""All ORM models (SQLAlchemy 2.0 style). PostgreSQL in production, SQLite for dev/tests."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


# --------------------------------- enums ---------------------------------- #
class ProjectStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    PENDING_ANALYSIS = "pending_analysis"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    RECOMMENDED = "recommended"          # score >= threshold, waiting for owner
    SKIPPED = "skipped"                  # score < threshold (AI recommendation)
    APPROVED_FOR_PROPOSAL = "approved_for_proposal"
    REJECTED_BY_OWNER = "rejected_by_owner"
    PROPOSAL_GENERATING = "proposal_generating"
    PROPOSAL_READY = "proposal_ready"
    PROPOSAL_SUBMITTED = "proposal_submitted"
    ANALYSIS_FAILED = "analysis_failed"
    UNAVAILABLE = "unavailable"


class Recommendation(str, enum.Enum):
    BID = "BID"
    SKIP = "SKIP"


class ProposalStatus(str, enum.Enum):
    GENERATING = "generating"
    READY = "ready"
    SUBMITTED = "submitted"
    SUBMIT_FAILED = "submit_failed"


class SubmissionMethod(str, enum.Enum):
    API = "api"
    ASSISTED = "assisted"
    MANUAL = "manual"


class SubmissionStatus(str, enum.Enum):
    ASSISTED_PENDING = "assisted_pending"      # waiting for owner to post manually
    SUBMITTED = "submitted"                    # confirmed (by platform API or owner)
    FAILED = "failed"
    ASSISTED_CONFIRMED = "submitted"           # owner confirmed the manual post


# --------------------------------- users ---------------------------------- #
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# -------------------------------- platforms -------------------------------- #
class Platform(Base):
    __tablename__ = "platforms"
    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    base_url: Mapped[str] = mapped_column(String(256), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    scan_interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_projects_per_scan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown")
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    credentials: Mapped["PlatformCredential | None"] = relationship(
        back_populates="platform", uselist=False, lazy="selectin")


class PlatformCredential(Base):
    __tablename__ = "platform_credentials"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id", ondelete="CASCADE"), unique=True)
    encrypted_payload: Mapped[str] = mapped_column(Text, default="")  # Fernet(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    platform: Mapped[Platform] = relationship(back_populates="credentials")


class PlatformScanLog(Base):
    __tablename__ = "platform_scan_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running|success|failed
    trigger: Mapped[str] = mapped_column(String(16), default="scheduler")  # scheduler|manual
    projects_found: Mapped[int] = mapped_column(Integer, default=0)
    projects_new: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    filtered: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------------- projects -------------------------------- #
class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(128))
    canonical_url: Mapped[str] = mapped_column(String(512))
    title: Mapped[str] = mapped_column(String(512))
    description: Mapped[str] = mapped_column(Text, default="")
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="IRT")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    client_info: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DISCOVERED.value, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("platform_id", "external_id", name="uq_projects_platform_external"),
        Index("ix_projects_canonical_url", "canonical_url"),
        Index("ix_projects_content_hash", "content_hash"),
    )


class ProjectAnalysis(Base):
    __tablename__ = "project_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    match_score: Mapped[int] = mapped_column(Integer, default=0)
    recommendation: Mapped[str] = mapped_column(String(8), default="SKIP")  # BID | SKIP
    reasoning: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    aggressive_bid: Mapped[dict] = mapped_column(JSON, default=dict)   # {price, delivery_days, rationale}
    balanced_bid: Mapped[dict] = mapped_column(JSON, default=dict)
    premium_bid: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matching_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_required_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_optional_skills: Mapped[list] = mapped_column(JSON, default=list)
    technical_complexity: Mapped[str] = mapped_column(String(16), default="unknown")
    scope_complexity: Mapped[str] = mapped_column(String(16), default="unknown")
    technical_risks: Mapped[list] = mapped_column(JSON, default=list)
    scope_risks: Mapped[list] = mapped_column(JSON, default=list)
    budget_feasibility: Mapped[str] = mapped_column(String(16), default="unknown")
    deadline_feasibility: Mapped[str] = mapped_column(String(16), default="unknown")
    client_quality: Mapped[dict] = mapped_column(JSON, default=dict)   # {score, evidence}
    clarification_questions: Mapped[list] = mapped_column(JSON, default=list)
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)            # token usage
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# -------------------------------- proposals -------------------------------- #
class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default=ProposalStatus.GENERATING.value)
    selected_strategy: Mapped[str] = mapped_column(String(16), default="balanced")  # aggressive|balanced|premium
    current_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    versions: Mapped[list["ProposalVersion"]] = relationship(back_populates="proposal", order_by="ProposalVersion.version_no")
    submission: Mapped["ProposalSubmission | None"] = relationship(back_populates="proposal", uselist=False)


class ProposalVersion(Base):
    __tablename__ = "proposal_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1)        # AI generation attempt (<= max)
    source: Mapped[str] = mapped_column(String(16), default="ai")      # ai | edited
    content: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    strategy: Mapped[str] = mapped_column(String(16), default="balanced")
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_report: Mapped[dict] = mapped_column(JSON, default=dict)   # {score, issues, strengths}
    model_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    proposal: Mapped[Proposal] = relationship(back_populates="versions")


class ProposalSubmission(Base):
    __tablename__ = "proposal_submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id", ondelete="CASCADE"), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    platform_id: Mapped[int] = mapped_column(ForeignKey("platforms.id"))
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="IRT")
    method: Mapped[str] = mapped_column(String(16), default=SubmissionMethod.ASSISTED.value)
    status: Mapped[str] = mapped_column(String(32), default=SubmissionStatus.ASSISTED_PENDING.value)
    external_submission_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)  # None|won|lost (only with evidence)
    outcome_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    preflight_report: Mapped[dict] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    proposal: Mapped[Proposal] = relationship(back_populates="submission")


# ------------------------------- AI providers ------------------------------ #
class AIProvider(Base):
    __tablename__ = "ai_providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    provider_type: Mapped[str] = mapped_column(String(32))  # openai_compatible | anthropic | ollama
    base_url: Mapped[str] = mapped_column(String(256))
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="")
    models: Mapped[list] = mapped_column(JSON, default=list)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown")
    cost_per_1k_input: Mapped[float | None] = mapped_column(Float, nullable=True)   # optional, for cost estimates
    cost_per_1k_output: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_test_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------- agent configuration -------------------------- #
class AgentConfiguration(Base):
    __tablename__ = "agent_configurations"
    id: Mapped[int] = mapped_column(primary_key=True)
    scan_interval_minutes: Mapped[int] = mapped_column(Integer, default=20)
    max_projects_per_scan: Mapped[int] = mapped_column(Integer, default=30)
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    # filters = {include_keywords: [], exclude_keywords: [], categories: [], budget_min: None,
    #            budget_max: None, currencies: []}
    min_recommendation_score: Mapped[int] = mapped_column(Integer, default=70)
    quality_threshold: Mapped[int] = mapped_column(Integer, default=75)
    max_generation_attempts: Mapped[int] = mapped_column(Integer, default=2)
    pricing_strategies: Mapped[dict] = mapped_column(JSON, default=dict)
    model_assignments: Mapped[dict] = mapped_column(JSON, default=dict)
    # {analyzer: {provider_id, model}, proposal: {...}, quality: {...}, copilot: {...}}
    copilot_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ---------------------------------- prompts -------------------------------- #
class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(32), unique=True)  # analyzer | proposal | quality | copilot
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["PromptVersion"]] = relationship(back_populates="prompt", order_by="PromptVersion.version_no.desc()")
    active_version: Mapped["PromptVersion | None"] = relationship(
        primaryjoin="foreign(PromptVersion.prompt_id)==Prompt.id and PromptVersion.is_active==True", uselist=False, viewonly=True
    )


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("prompts.id", ondelete="CASCADE"), index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    prompt: Mapped[Prompt] = relationship(back_populates="versions")
    __table_args__ = (UniqueConstraint("prompt_id", "version_no", name="uq_prompt_versions_no"),)


# ------------------------------- notifications ----------------------------- #
class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)  # project.new|analysis.done|proposal.ready|submission|system
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    id: Mapped[int] = mapped_column(primary_key=True)
    web_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sound_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    volume: Mapped[float] = mapped_column(Float, default=0.6)
    browser_notifications: Mapped[bool] = mapped_column(Boolean, default=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    min_score_to_notify: Mapped[int] = mapped_column(Integer, default=0)  # 0 = notify for everything
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# --------------------------------- outbox ---------------------------------- #
class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|processing|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=8)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(16), default="info", index=True)  # debug|info|warning|error
    component: Mapped[str] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ----------------------------- developer profile --------------------------- #
class DeveloperProfile(Base):
    __tablename__ = "developer_profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    github_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    portfolio_urls: Mapped[list] = mapped_column(JSON, default=list)
    experience_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    work_experience: Mapped[str] = mapped_column(Text, default="")
    completed_projects: Mapped[str] = mapped_column(Text, default="")
    preferred_categories: Mapped[list] = mapped_column(JSON, default=list)
    preferred_technologies: Mapped[list] = mapped_column(JSON, default=list)
    min_acceptable_budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(16), default="IRT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    skills: Mapped[list["DeveloperSkill"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class DeveloperSkill(Base):
    __tablename__ = "developer_skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("developer_profiles.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    level: Mapped[int] = mapped_column(Integer, default=3)  # 1..5 proficiency
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_core: Mapped[bool] = mapped_column(Boolean, default=False)

    profile: Mapped[DeveloperProfile] = relationship(back_populates="skills")
    __table_args__ = (UniqueConstraint("profile_id", "name", name="uq_developer_skills_name"),)


# --------------------------------- telegram -------------------------------- #
class TelegramSetting(Base):
    __tablename__ = "telegram_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    bot_token_encrypted: Mapped[str] = mapped_column(Text, default="")
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(16), default="polling")  # polling | webhook
    webhook_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pairing_code: Mapped[str] = mapped_column(String(16), default="")
    connection_status: Mapped[str] = mapped_column(String(32), default="disconnected")
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_min_score: Mapped[int] = mapped_column(Integer, default=60)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AuthorizedChatID(Base):
    __tablename__ = "authorized_chat_ids"
    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(64), unique=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    authorized: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserSetting(Base):
    __tablename__ = "user_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
