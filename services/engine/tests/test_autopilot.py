"""Piloto automático: escolhe os cortes em alta, legenda com # por rede, rodízio de redes, limite do mês e nuvem."""
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from stark_engine import autopilot
from stark_engine.cloud import Supa
from stark_engine.db import session_scope
from stark_engine.models import ClipCandidate, EditedClip, RightsGrant, SourceVideo, Trend, Workspace, utcnow
from stark_engine.security import deep_merge, rel_data

PUB = "sb_publishable_teste_0123456789"


class FakeSupa:
    """Imita o Supabase: rpc do PC (pasta secreta), upload, link assinado e remoção."""

    def __init__(self):
        self.folder, self.queue, self.posted, self.objects, self.secret = "f0lder", None, [], {}, None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.headers.get("apikey") != PUB:
            return httpx.Response(401)
        path = req.url.path
        if path == "/rest/v1/rpc/clipzou_pc_hello":
            s = json.loads(req.content)["p_secret"]
            if self.secret and s != self.secret:
                return httpx.Response(400, json={"message": "outro PC"})
            self.secret = s
            return httpx.Response(200, json=self.folder)
        if path == "/rest/v1/rpc/clipzou_pc_push":
            a = json.loads(req.content)
            assert a["p_secret"] == self.secret
            self.queue = a["p_queue"]
            return httpx.Response(200, json={"posts": self.posted})
        if path.startswith("/storage/v1/object/sign/clipzou/"):
            obj = path.removeprefix("/storage/v1/object/sign/clipzou/")
            assert obj in self.objects
            return httpx.Response(200, json={"signedURL": f"/object/sign/clipzou/{obj}?token=x"})
        if path.startswith("/storage/v1/object/clipzou/") and req.method == "POST":
            obj = path.removeprefix("/storage/v1/object/clipzou/")
            assert obj.startswith(f"pc/{self.folder}/") and "x-upsert" not in req.headers
            self.objects[obj] = req.read()
            return httpx.Response(200, json={"Key": obj})
        if path == "/storage/v1/object/clipzou" and req.method == "DELETE":
            for p in json.loads(req.content)["prefixes"]:
                self.objects.pop(p, None)
            return httpx.Response(200, json=[])
        return httpx.Response(404)


def _clip(data_dir, title: str, score: float, kw: list[str], commercial: bool = True) -> int:
    d = data_dir / "autopilot"
    d.mkdir(exist_ok=True)
    out, cover = d / f"{title}.mp4", d / f"{title}.jpg"
    out.write_bytes(b"\0" * 1000)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=540x960", "-frames:v", "1",
                    str(cover)], check=True)
    with session_scope() as s:
        v = SourceVideo(workspace_id=1, title=title, origin="upload", status="ready", niche="Grand Theft Auto VI")
        s.add(v)
        s.commit()
        s.add(RightsGrant(workspace_id=1, video_id=v.id, declared_by=1, rights_type="own", holder="eu",
                          allows_commercial=commercial))
        c = ClipCandidate(video_id=v.id, start_s=0, end_s=20, title=title, score=score, keywords=kw,
                          transcript_text=" ".join(kw))
        s.add(c)
        s.commit()
        ec = EditedClip(workspace_id=1, candidate_id=c.id, video_id=v.id, start_s=0, end_s=20, status="ready",
                        duration_s=20, output_path=rel_data(out), cover_path=rel_data(cover),
                        copy_text={"title": title, "captions": {
                            "tiktok": f"{title} #clipzou", "instagram": f"{title}", "facebook": f"{title}"}})
        s.add(ec)
        s.commit()
        return ec.id


@pytest.fixture
def clips(client, data_dir):
    if not shutil.which("ffmpeg"):
        pytest.skip("requer ffmpeg")
    with session_scope() as s:
        s.add(Trend(workspace_id=1, source="youtube_rss", kind="video", label="GTA 6 perseguição insana em Leonida",
                    url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
                    metric={"views": 900000, "published_at": (datetime.now(UTC) - timedelta(hours=3)).isoformat()}))
        s.commit()
    ids = [_clip(data_dir, "Fuga da policia em Leonida", 70, ["leonida", "perseguicao", "policia"]),
           _clip(data_dir, "Receita de bolo", 75, ["bolo", "receita"]),
           _clip(data_dir, "Melhor salto do mapa", 72, ["salto", "mapa"]),
           _clip(data_dir, "Sem permissao comercial", 99, ["leonida"], commercial=False)]
    yield ids
    with session_scope() as s:
        for cid in ids:
            ec = s.get(EditedClip, cid)
            if ec:
                ec.status = "draft"
                s.add(ec)
        s.commit()


def test_trend_boost_and_rights(clips):
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        picks = autopilot.eligible(s, ws)
    ids = [p.clip_id for p in picks]
    assert clips[3] not in ids  # sem permissão comercial não posta no seu perfil
    assert ids.index(clips[0]) < ids.index(clips[1])  # assunto em alta (Leonida) passa na frente de nota maior
    top = next(p for p in picks if p.clip_id == clips[0])
    assert "#leonida" in top.trend_tags


def test_plan_rotates_networks_respects_month_and_adds_tags(clips):
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        q = autopilot.plan(s, ws, [])
        assert [i["network"] for i in q["items"]] == ["tiktok", "instagram", "facebook"]
        assert len({i["clip_id"] for i in q["items"]}) == 3 and q["items"][0]["clip_id"] == clips[0]
        assert "#leonida" in q["items"][0]["caption"] and "#clipzou" in q["items"][0]["caption"]
        month = datetime.now(UTC).strftime("%Y-%m")
        used = [{"clip_id": 999, "network": "tiktok", "month": month}] * 17
        q2 = autopilot.plan(s, ws, used)
        assert len(q2["items"]) == 1 and q2["items"][0]["network"] == "instagram"  # 18º do mês, depois do tiktok
        ws.settings = deep_merge(ws.settings or {}, {"autopilot": {"enabled": False}})
        s.add(ws)
        s.commit()
        assert autopilot.plan(s, ws, [])["items"] == []
        ws.settings = deep_merge(ws.settings or {}, {"autopilot": {"enabled": True}})
        s.add(ws)
        s.commit()


def test_sync_uploads_queue_signs_and_cleans_posted(clips):
    fake = FakeSupa()
    client = Supa("https://abc.supabase.co", PUB, httpx.MockTransport(fake))
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        r = autopilot.sync(s, ws, client)
    assert len(r["items"]) == 3 and fake.queue["items"][0]["media_url"].startswith(
        "https://abc.supabase.co/storage/v1/object/sign/clipzou/pc/f0lder/")
    assert len(fake.objects) == 6  # 3 vídeos + 3 miniaturas, só os da fila
    first = fake.queue["items"][0]
    fake.posted = [{"clip_id": first["clip_id"], "network": first["network"],
                    "month": datetime.now(UTC).strftime("%Y-%m"), "at": utcnow().isoformat()}]
    with session_scope() as s:
        ws = s.get(Workspace, 1)
        r2 = autopilot.sync(s, ws, client)
    ids2 = [i["clip_id"] for i in r2["items"]]
    assert first["clip_id"] not in ids2 and r2["used_this_month"] == 1  # já postado sai da fila e da nuvem
    assert not any(o.split("/")[-1].startswith(f"{first['clip_id']}-") for o in fake.objects)


def test_scheduled_post_keeps_video_until_it_goes_out(clips):
    fake = FakeSupa()
    client = Supa("https://abc.supabase.co", PUB, httpx.MockTransport(fake))
    with session_scope() as s:
        autopilot.sync(s, s.get(Workspace, 1), client)
    first = fake.queue["items"][0]
    later = (datetime.now(UTC) + timedelta(hours=20)).isoformat()
    fake.posted = [{"clip_id": first["clip_id"], "network": first["network"], "scheduled_for": later,
                    "month": datetime.now(UTC).strftime("%Y-%m")}]
    with session_scope() as s:
        r = autopilot.sync(s, s.get(Workspace, 1), client)
    assert first["clip_id"] not in [i["clip_id"] for i in r["items"]]  # não agenda de novo
    assert any(o.split("/")[-1].startswith(f"{first['clip_id']}-") for o in fake.objects)  # vídeo continua lá
