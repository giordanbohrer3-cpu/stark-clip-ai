"""Contratos da API v1 (entrada/saída tipadas)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models import (
    AnalyticsSnapshotBase,
    ClipCandidateRead,
    EditedClipRead,
    JobRead,
    RightsGrantRead,
    ScheduledPostRead,
    SourceVideoRead,
)

Layout = Literal["auto", "face", "center", "split", "fit"]
Platform = Literal["tiktok", "instagram", "facebook", "youtube"]


def naive_utc(v: datetime | None) -> datetime | None:
    """Normaliza entrada para UTC aware (sem tz = assume UTC)."""
    if v is None:
        return v
    return v.replace(tzinfo=UTC) if v.tzinfo is None else v.astimezone(UTC)


class ReferenceIn(BaseModel):
    url: str = Field(max_length=500)
    niche: str = ""


class VideoPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    niche: str | None = Field(default=None, max_length=80)
    favorite: bool | None = None


class RightsIn(BaseModel):
    rights_type: Literal["own", "licensed", "creator_permission", "public_domain", "cc_by"]
    holder: str = Field(min_length=2, max_length=120)
    evidence: str = Field(default="", max_length=1000)
    allows_edit: bool = True
    allows_commercial: bool = False
    expires_at: datetime | None = None
    confirm: bool = False
    _v = field_validator("expires_at")(lambda cls, v: naive_utc(v))


class ProcessIn(BaseModel):
    mode: Literal["short", "long"] | None = None


class CandidatePatch(BaseModel):
    status: Literal["candidate", "approved", "rejected"] | None = None
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=150)


class EditPatch(BaseModel):
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, gt=0)
    layout: Layout | None = None
    remove_pauses: bool | None = None
    denoise: bool | None = None
    logo: bool | None = None
    caption_style: dict | None = None
    words_override: list[list] | None = None
    copy_text: dict | None = None


class RenderIn(BaseModel):
    preview: bool = False


class CutsImport(BaseModel):
    cuts: list[dict] = Field(max_length=10)


class AccountIn(BaseModel):
    platform: Platform
    handle: str = Field(min_length=1, max_length=60)
    display_name: str = Field(default="", max_length=80)
    niche: str = Field(default="", max_length=80)
    bio: str = Field(default="", max_length=300)
    niche_hashtags: list[str] = Field(default_factory=list, max_length=10)
    daily_cap: int = Field(default=5, ge=1, le=10)


class AccountPatch(BaseModel):
    display_name: str | None = None
    niche: str | None = None
    bio: str | None = Field(default=None, max_length=300)
    niche_hashtags: list[str] | None = None
    daily_cap: int | None = Field(default=None, ge=1, le=10)
    status: Literal["needs_oauth", "paused"] | None = None


class PostIn(BaseModel):
    edited_clip_id: int
    account_id: int
    scheduled_at: datetime | None = None
    title: str | None = None
    caption: str | None = None
    hashtags: list[str] | None = None
    mode: Literal["assisted", "export", "api"] = "assisted"
    _v = field_validator("scheduled_at")(lambda cls, v: naive_utc(v))


class PostPatch(BaseModel):
    approved: bool | None = None
    scheduled_at: datetime | None = None
    caption: str | None = Field(default=None, max_length=5000)
    hashtags: list[str] | None = None
    status: Literal["canceled", "published"] | None = None
    external_url: str | None = Field(default=None, max_length=500)
    _v = field_validator("scheduled_at")(lambda cls, v: naive_utc(v))


class BulkScheduleIn(BaseModel):
    edited_clip_ids: list[int] = Field(min_length=1, max_length=50)
    account_ids: list[int] = Field(min_length=1, max_length=20)
    mode: Literal["assisted", "export", "api"] = "assisted"


class SnapshotIn(AnalyticsSnapshotBase):
    pass


class TrendIn(BaseModel):
    kind: Literal["topic", "hashtag", "audio", "format", "video"] = "topic"
    label: str = Field(min_length=1, max_length=200)
    url: str | None = None
    region: str = "BR"
    source: str = "manual"
    confidence: float = Field(default=0.5, ge=0, le=1)
    license_note: str = ""


class SettingsPatch(BaseModel):
    data: dict


class VideoDetail(BaseModel):
    video: SourceVideoRead
    rights: list[RightsGrantRead]
    candidates: list[ClipCandidateRead]
    clips: list[EditedClipRead]
    jobs: list[JobRead]
    transcript: dict | None = None


class PostRow(ScheduledPostRead):
    account_handle: str = ""
    clip_title: str = ""
    upload_url: str | None = None


class Stats(BaseModel):
    videos: dict
    clips: dict
    jobs: dict
    posts: dict
    analytics: dict
    ai: dict
    storage_mb: float
    alerts: list[str]


class Health(BaseModel):
    ok: bool
    version: str
    ffmpeg: bool
    db: bool
    whisper_model: str
    youtube_api: bool
    providers: list[dict] = []
