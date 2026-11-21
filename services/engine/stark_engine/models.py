"""Entidades persistentes. Padrão SQLModel: XBase (campos públicos) -> X (tabela) -> XRead (API).

Mapeamento de nomes do plano: RenderJob = Job(kind="render"), PublishingJob = Job(kind="publish").
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """UTC com tzinfo (SQLModel exige datetime aware; API serializa com +00:00)."""
    return datetime.now(UTC)


def _json(default: Any = None) -> Any:
    factory = (dict) if default is None else (lambda: list(default))
    return Field(default_factory=factory, sa_column=Column(JSON, nullable=False))


# ---------------------------------------------------------------- workspace / users
class Workspace(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    settings: dict = _json()
    created_at: datetime = Field(default_factory=utcnow)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    name: str
    role: str = "owner"  # owner|editor|viewer
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- social accounts
class SocialAccountBase(SQLModel):
    platform: str = Field(index=True)  # tiktok|instagram|facebook|youtube
    handle: str
    display_name: str = ""
    niche: str = ""
    bio: str = ""
    niche_hashtags: list = _json([])
    daily_cap: int = 5
    status: str = "needs_oauth"  # needs_oauth|connected|error|paused


class SocialAccount(SocialAccountBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    token_encrypted: str | None = None  # Fernet; nunca exposto pela API
    token_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class SocialAccountRead(SocialAccountBase):
    id: int
    created_at: datetime


# ---------------------------------------------------------------- videos & direitos
class SourceVideoBase(SQLModel):
    title: str
    origin: str = "upload"  # upload|library|youtube_ref
    youtube_id: str | None = Field(default=None, index=True)
    url: str | None = None
    thumbnail_url: str | None = None
    channel: str | None = None
    niche: str = ""
    duration_s: float = 0
    width: int = 0
    height: int = 0
    fps: float = 0
    has_audio: bool = False
    size_bytes: int = 0
    status: str = Field(default="uploaded", index=True)  # reference|uploaded|queued|analyzing|ready|error
    error: str | None = None
    favorite: bool = False


class SourceVideo(SourceVideoBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    file_path: str | None = None
    file_hash: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class SourceVideoRead(SourceVideoBase):
    id: int
    created_at: datetime
    has_file: bool = False
    rights_ok: bool = False


class RightsGrantBase(SQLModel):
    rights_type: str  # own|licensed|creator_permission|public_domain|cc_by
    holder: str
    evidence: str = ""
    allows_edit: bool = True
    allows_commercial: bool = False
    expires_at: datetime | None = None


class RightsGrant(RightsGrantBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    video_id: int = Field(foreign_key="sourcevideo.id", index=True)
    declared_by: int = Field(foreign_key="user.id")
    declared_at: datetime = Field(default_factory=utcnow)


class RightsGrantRead(RightsGrantBase):
    id: int
    declared_at: datetime


class Transcript(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="sourcevideo.id", index=True)
    file_hash: str = Field(index=True)
    model: str
    language: str
    text: str
    words: list = _json([])  # [[start, end, word, prob], ...]
    segments: list = _json([])  # [[start, end, text], ...]
    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------- cortes
class ClipCandidateBase(SQLModel):
    rank: int = 0
    start_s: float
    end_s: float
    title: str = ""
    summary: str = ""
    justification: str = ""
    hook: str = ""
    score: float = 0  # heurística explicável 0-100, não é promessa de viralização
    score_breakdown: dict = _json()
    keywords: list = _json([])
    transcript_text: str = ""
    source: str = "heuristic"  # heuristic|llm:<provider>|operator
    status: str = "candidate"  # candidate|approved|rejected


class ClipCandidate(ClipCandidateBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: int = Field(foreign_key="sourcevideo.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


class ClipCandidateRead(ClipCandidateBase):
    id: int
    video_id: int
    duration_s: float = 0


class EditedClipBase(SQLModel):
    start_s: float
    end_s: float
    layout: str = "auto"  # auto|face|center|split|fit
    remove_pauses: bool = False
    denoise: bool = False
    logo: bool = True
    caption_style: dict = _json()
    words_override: list = _json([])  # palavras revisadas manualmente
    status: str = "draft"  # draft|rendering|ready|error
    error: str | None = None
    duration_s: float = 0
    layout_used: str | None = None
    copy_text: dict = _json()  # {title, captions:{platform:txt}, hashtags:[...]} gerado


class EditedClip(EditedClipBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    candidate_id: int = Field(foreign_key="clipcandidate.id", index=True)
    video_id: int = Field(foreign_key="sourcevideo.id", index=True)
    output_path: str | None = None
    preview_path: str | None = None
    srt_path: str | None = None
    ass_path: str | None = None
    cover_path: str | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class EditedClipRead(EditedClipBase):
    id: int
    candidate_id: int
    video_id: int
    updated_at: datetime
    files: list[str] = []


# ---------------------------------------------------------------- fila de jobs
class JobBase(SQLModel):
    kind: str = Field(index=True)  # analyze|render|publish
    ref_id: int = Field(index=True)
    status: str = Field(default="queued", index=True)  # queued|running|done|error|canceled
    stage: str = ""
    progress: float = 0
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    cancel_requested: bool = False
    payload: dict = _json()
    result: dict = _json()


class Job(JobBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    run_after: datetime | None = Field(default=None, index=True)
    lease_until: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobRead(JobBase):
    id: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


# ---------------------------------------------------------------- publicações
class ScheduledPostBase(SQLModel):
    platform: str
    title: str = ""
    caption: str = ""
    hashtags: list = _json([])
    scheduled_at: datetime = Field(index=True)
    mode: str = "assisted"  # assisted|export|api
    status: str = Field(default="scheduled", index=True)
    # scheduled|queued|publishing|ready_manual|exported|published|failed|blocked|canceled
    approved: bool = False
    external_url: str | None = None
    error: str | None = None


class ScheduledPost(ScheduledPostBase, table=True):
    __table_args__ = (UniqueConstraint("edited_clip_id", "account_id", name="uq_post_clip_account"),)
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    edited_clip_id: int = Field(foreign_key="editedclip.id", index=True)
    account_id: int = Field(foreign_key="socialaccount.id", index=True)
    content_hash: str = Field(index=True)
    export_dir: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    published_at: datetime | None = None


class ScheduledPostRead(ScheduledPostBase):
    id: int
    edited_clip_id: int
    account_id: int
    created_at: datetime
    published_at: datetime | None = None
    export_dir: str | None = None


# ---------------------------------------------------------------- inteligência
class TrendBase(SQLModel):
    source: str  # youtube_api|manual|vidiq|creative_center(manual)
    region: str = "BR"
    kind: str = "topic"  # topic|hashtag|audio|format|video
    label: str
    url: str | None = None
    metric: dict = _json()
    confidence: float = 0.5  # 0-1, quão confiável é a fonte/dado
    license_note: str = ""


class Trend(TrendBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    fetched_at: datetime = Field(default_factory=utcnow)


class TrendRead(TrendBase):
    id: int
    fetched_at: datetime


class AnalyticsSnapshotBase(SQLModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    followers_gained: int = 0
    watch_time_s: float = 0
    retention_pct: float | None = None
    revenue: float | None = None
    source: str = "manual"  # manual|api
    kind: str = "observed"  # observed|confirmed|projection


class AnalyticsSnapshot(AnalyticsSnapshotBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="scheduledpost.id", index=True)
    captured_at: datetime = Field(default_factory=utcnow)


class AIUsage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    provider: str
    model: str
    task: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0  # estimativa pela tabela de preços configurável
    ok: bool = True
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow, index=True)


class AuditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    actor: str  # user:<id>|agent|system
    action: str = Field(index=True)
    target: str = ""
    detail: dict = _json()
    created_at: datetime = Field(default_factory=utcnow, index=True)


# ---------------------------------------------------------------- radar ao vivo / máquina de clipes
class Integration(SQLModel, table=True):
    """Conta externa conectada via OAuth (ex.: Twitch). Tokens criptografados (Fernet)."""
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    provider: str = Field(index=True)
    account_id: str = ""
    account_login: str = ""
    token_encrypted: str | None = None
    refresh_encrypted: str | None = None
    expires_at: datetime | None = None
    scopes: list = _json([])
    updated_at: datetime = Field(default_factory=utcnow)


class ChannelGrantBase(SQLModel):
    platform: str = "twitch"
    channel: str = Field(index=True)  # login em minúsculas
    display_name: str = ""
    rights_type: str = "creator_permission"  # creator_permission|campaign|own
    evidence: str = ""  # link do programa de clipes, print, contrato
    allows_commercial: bool = True
    auto_clip: bool = True
    active: bool = True


class ChannelGrant(ChannelGrantBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    broadcaster_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ChannelGrantRead(ChannelGrantBase):
    id: int
    created_at: datetime


class LiveStreamBase(SQLModel):
    platform: str = "twitch"
    channel: str = Field(index=True)
    display_name: str = ""
    title: str = ""
    viewers: int = 0
    game: str = ""
    language: str = ""
    thumbnail_url: str = ""
    url: str = ""
    live: bool = Field(default=True, index=True)


class LiveStream(LiveStreamBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)
    broadcaster_id: str | None = None
    started_at: datetime | None = None
    seen_at: datetime = Field(default_factory=utcnow, index=True)


class LiveStreamRead(LiveStreamBase):
    id: int
    seen_at: datetime
    authorized: bool = False


class LiveMomentBase(SQLModel):
    platform: str = "twitch"
    channel: str = Field(index=True)
    at: datetime = Field(default_factory=utcnow, index=True)
    rate: float = 0
    baseline: float = 0
    score: float = 0
    viewers: int = 0
    tokens: list = _json([])
    samples: list = _json([])
    status: str = "detected"  # detected|clipping|processing|ready|failed|skipped
    clip_id: str | None = None
    video_id: int | None = None
    error: str | None = None


class LiveMoment(LiveMomentBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    workspace_id: int = Field(foreign_key="workspace.id", index=True)


class LiveMomentRead(LiveMomentBase):
    id: int
    authorized: bool = False
    watch_url: str = ""
