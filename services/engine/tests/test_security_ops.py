"""Segurança, fila, orçamento de IA e publicação (sem rede externa)."""
from datetime import timedelta
from itertools import pairwise

import pytest
from fastapi import HTTPException

from stark_engine import jobqueue
from stark_engine.ai.providers import AIError, BudgetExceeded, call_json
from stark_engine.db import session_scope
from stark_engine.models import Job, SocialAccount, Workspace, utcnow
from stark_engine.publishing import next_slots
from stark_engine.security import deep_merge, safe_path
from stark_engine.youtube import YouTubeError, parse_id

from .conftest import AUTH


def test_auth_required(client):
    assert client.get("/api/v1/videos").status_code == 401
    assert client.get("/api/v1/videos", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/v1/health").json()["ffmpeg"] is True


@pytest.mark.parametrize("name,content,code", [
    ("x.exe", b"MZ", 415), ("x.mp4", b"not a video", 422)], ids=["bad-ext", "not-media"])
def test_upload_validation(client, name, content, code):
    r = client.post("/api/v1/videos/upload", headers=AUTH, files={"file": (name, content)},
                    data={"rights_type": "own", "holder": "Eu", "confirm": "true"})
    assert r.status_code == code


def test_upload_requires_rights_confirmation(client):
    r = client.post("/api/v1/videos/upload", headers=AUTH, files={"file": ("a.mp4", b"x")},
                    data={"rights_type": "own", "holder": "Eu", "confirm": "false"})
    assert r.status_code == 422


@pytest.mark.parametrize("url", ["https://evil.com/watch?v=dQw4w9WgXcQ", "http://169.254.169.254/latest",
                                 "https://youtube.com.evil.io/watch?v=dQw4w9WgXcQ", "https://youtu.be/short"])
def test_youtube_ssrf_guard(url):
    with pytest.raises(YouTubeError):
        parse_id(url)


@pytest.mark.parametrize("url", ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ",
                                 "https://youtube.com/shorts/dQw4w9WgXcQ"])
def test_youtube_parse_ok(url):
    assert parse_id(url) == "dQw4w9WgXcQ"


def test_safe_path_traversal(data_dir):
    with pytest.raises(HTTPException):
        safe_path(data_dir, "../../etc/passwd")
    assert safe_path(data_dir, "media", "1") == data_dir / "media" / "1"


def test_free_only_blocks_paid_providers(client):
    body = {"data": {"ai": {"providers": {"anthropic": {"enabled": True}}}}}
    assert client.patch("/api/v1/settings?confirm_paid=true", headers=AUTH, json=body).status_code == 403
    route = {"data": {"ai": {"routing": {"cut_planning": "openai"}}}}
    assert client.patch("/api/v1/settings", headers=AUTH, json=route).status_code == 403
    st = client.get("/api/v1/settings", headers=AUTH).json()
    assert st["env"]["free_only"] is True
    assert {p["provider"] for p in st["providers"] if p["blocked"]} == {"anthropic", "openai"}


def test_free_tier_gemini_costs_zero(monkeypatch, client):
    from stark_engine import ai
    monkeypatch.setattr(ai.providers, "_key", lambda p: "fake")
    monkeypatch.setattr(ai.providers, "_request", lambda *a, **k: ('{"ok": true}', 100, 20))
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        ws.settings = deep_merge(ws.settings or {}, {"ai": {"monthly_budget_usd": 0.0,
                                                            "providers": {"gemini": {"enabled": True}}}})
        s.add(ws)
        s.commit()
        assert call_json(s, ws, "gemini", "t", "sys", "prompt") == {"ok": True}
        with pytest.raises(AIError):
            call_json(s, ws, "anthropic", "t", "sys", "prompt")
        ws.settings = deep_merge(ws.settings, {"ai": {"providers": {"gemini": {"enabled": False}}}})
        s.add(ws)
        s.commit()
    usage = client.get("/api/v1/ai/usage", headers=AUTH).json()
    assert usage[0]["provider"] == "gemini" and usage[0]["cost_usd"] == 0


def test_paid_provider_requires_explicit_confirm(monkeypatch, client):
    from stark_engine.config import get_settings
    monkeypatch.setattr(get_settings(), "free_only", False)
    body = {"data": {"ai": {"providers": {"anthropic": {"enabled": True}}}}}
    assert client.patch("/api/v1/settings", headers=AUTH, json=body).status_code == 428
    r = client.patch("/api/v1/settings?confirm_paid=true", headers=AUTH, json=body)
    assert r.status_code == 200
    client.patch("/api/v1/settings", headers=AUTH, json={"data": {"ai": {"providers": {"anthropic": {"enabled": False}}}}})


def test_budget_hard_limit_blocks_before_call(monkeypatch, client):
    from stark_engine import ai
    from stark_engine.config import get_settings
    monkeypatch.setattr(get_settings(), "free_only", False)
    monkeypatch.setattr(ai.providers, "_key", lambda p: "fake")
    called = []
    monkeypatch.setattr(ai.providers, "_request", lambda *a, **k: called.append(1))
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        ws.settings = deep_merge(ws.settings or {}, {"ai": {"monthly_budget_usd": 0.0,
                                                            "providers": {"gemini": {"enabled": True}}}})
        s.add(ws)
        s.commit()
        with pytest.raises(BudgetExceeded):
            call_json(s, ws, "gemini", "t", "sys", "prompt")
        assert not called
        ws.settings = deep_merge(ws.settings, {"ai": {"providers": {"gemini": {"enabled": False}}}})
        s.add(ws)
        s.commit()
        with pytest.raises(AIError):
            call_json(s, ws, "gemini", "t", "sys", "prompt")


def test_queue_dedupe_claim_retry_cancel_pause(client):
    with session_scope() as s:
        s.exec(Job.__table__.delete())  # isolamento: fila limpa
        s.commit()
        a = jobqueue.enqueue(s, 1, "noop", 999)
        assert jobqueue.enqueue(s, 1, "noop", 999).id == a.id
        job = jobqueue.claim(s)
        assert job.id == a.id and job.status == "running" and job.attempts == 1
        jobqueue.fail(job.id, "boom", retryable=True)
        s.refresh(job)
        assert job.status == "queued" and job.run_after > utcnow()
        job.run_after = None
        s.add(job)
        s.commit()
        client.post("/api/v1/agent/pause", headers=AUTH)
        assert jobqueue.claim(s) is None  # pausa global bloqueia
        client.post("/api/v1/agent/resume", headers=AUTH)
        job = jobqueue.claim(s)
        job.lease_until = utcnow() - timedelta(seconds=5)
        s.add(job)
        s.commit()
        assert jobqueue.recover_stale(s) == 1  # worker morto -> volta p/ fila
        s.refresh(job)
        jobqueue.request_cancel(s, job)
        assert job.status == "canceled"


def test_slots_respect_cap_gap_and_quiet_hours(client):
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        acc = SocialAccount(workspace_id=1, platform="tiktok", handle="@teste", daily_cap=3)
        s.add(acc)
        s.commit()
        slots = next_slots(s, ws, acc, 10)
        assert len(slots) == 10
        for a, b in pairwise(slots):
            assert (b - a) >= timedelta(minutes=90)
        per_day: dict = {}
        for t in slots:
            local = t + timedelta(hours=-3)
            assert not (0 <= local.hour < 7)
            per_day[local.date()] = per_day.get(local.date(), 0) + 1
        assert max(per_day.values()) <= 3
        s.exec(Job.__table__.delete())
        s.commit()
