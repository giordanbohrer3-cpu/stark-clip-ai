"""Ponte PC → nuvem com um Supabase falso: radar só com mudanças, pedidos do celular, cortes e limite de espaço."""
import json
import shutil
import subprocess
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from stark_engine import cloud
from stark_engine.db import session_scope
from stark_engine.main import app
from stark_engine.models import ClipCandidate, EditedClip, SourceVideo, utcnow
from stark_engine.security import rel_data

from .conftest import AUTH

KEY = "sb_secret_" + "x" * 30


class FakeSupa:
    def __init__(self):
        self.snap, self.clips, self.cmds, self.objects, self.egress = {}, {}, [], {}, 0

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.headers.get("apikey") != KEY or "authorization" in req.headers:
            return httpx.Response(401, json={"message": "bad key"})
        path = req.url.path
        if path.startswith("/rest/v1/rpc/"):
            a = json.loads(req.content or b"{}")
            return httpx.Response(200, json=getattr(self, path.rsplit("/", 1)[1])(**a))
        if path.startswith("/storage/v1/object/clipzou/") and req.method == "POST":
            self.objects[path.removeprefix("/storage/v1/object/clipzou/")] = req.read()
            return httpx.Response(200, json={"Key": path})
        if path == "/storage/v1/object/clipzou" and req.method == "DELETE":
            for p in json.loads(req.content)["prefixes"]:
                self.objects.pop(p, None)
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    def clipzou_push(self, p):
        self.snap.update(p)

    def clipzou_cmd_take(self, p_limit):
        out = [c for c in self.cmds if c["status"] == "pending"][:p_limit]
        for c in out:
            c["status"] = "taken"
        return [{k: c[k] for k in ("id", "method", "path", "body")} for c in out]

    def clipzou_cmd_done(self, p_id, p_http, p_result):
        c = next(c for c in self.cmds if c["id"] == p_id)
        c.update(status="done" if p_http < 400 else "error", http=p_http, result=p_result)

    def clipzou_clip_upsert(self, p):
        self.clips[p["id"]] = p

    def clipzou_clip_delete(self, p_ids):
        gone = [self.clips.pop(i) for i in p_ids if i in self.clips]
        return [x for c in gone for x in (c["output_path"], c["cover_path"]) if x]

    def clipzou_egress(self):
        return self.egress


@pytest.fixture
def fake():
    return FakeSupa()


@pytest.fixture
def syncer(client, fake, data_dir):
    for f in (cloud.STATE_FILE, cloud.STATUS_FILE):
        (data_dir / f).unlink(missing_ok=True)
    local = TestClient(app, base_url="http://testserver/api/v1", headers=AUTH)
    return cloud.Syncer(local, cloud.Supa("https://abc.supabase.co", KEY, httpx.MockTransport(fake)))


def test_allowed_list():
    assert cloud.allowed("POST", "/inbox/scan") and cloud.allowed("post", "/live/channels/12/clip")
    assert not cloud.allowed("DELETE", "/videos/3") and not cloud.allowed("POST", "/inbox/scan/../x")
    assert not cloud.allowed("GET", "/inbox/scan")


def test_snapshot_pushes_only_changes_and_beat(syncer, fake):
    assert syncer.snapshot() == len(cloud.SNAP)
    assert {"status", "streams", "videos", "inbox", "queue", "settings", "rev"} <= set(fake.snap)
    assert fake.snap["status"]["game"] == "Grand Theft Auto VI" and "beat" in fake.snap["rev"]
    beat = fake.snap["rev"]["beat"]
    fake.snap.pop("status")
    assert syncer.snapshot() == 0  # nada mudou: só o batimento (PC online)
    assert "status" not in fake.snap and fake.snap["rev"]["beat"] >= beat


def test_phone_commands_run_on_pc_with_allowlist(syncer, fake):
    fake.cmds = [{"id": 1, "method": "POST", "path": "/inbox/scan", "body": None, "status": "pending"},
                 {"id": 2, "method": "DELETE", "path": "/videos/1", "body": None, "status": "pending"},
                 {"id": 3, "method": "PATCH", "path": "/settings", "body": {"data": {"radar": {"min_rate": 14}}},
                  "status": "pending"}]
    assert syncer.commands() == 3
    one, two, three = fake.cmds
    assert one["http"] == 200 and one["result"]["status"] == "aguardando declaração"
    assert two["http"] == 403 and two["status"] == "error"  # apagar vídeo: só no PC
    assert three["http"] == 200 and three["result"]["settings"]["radar"]["min_rate"] == 14
    assert syncer.force  # resposta rápida: radar sobe logo depois


def _ready_clip(data_dir, title: str, minutes_ago: int, size: int) -> int:
    d = data_dir / "cloudtest"
    d.mkdir(exist_ok=True)
    out = d / f"{title}.mp4"
    out.write_bytes(b"\0" * size)
    cover = d / f"{title}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=1080x1920", "-frames:v", "1",
                    str(cover)], check=True)
    with session_scope() as s:
        v = SourceVideo(workspace_id=1, title=title, origin="upload", status="ready")
        s.add(v)
        s.commit()
        c = ClipCandidate(video_id=v.id, start_s=0, end_s=20, title=title)
        s.add(c)
        s.commit()
        ec = EditedClip(workspace_id=1, candidate_id=c.id, video_id=v.id, start_s=0, end_s=20, status="ready",
                        duration_s=20, output_path=rel_data(out), cover_path=rel_data(cover),
                        copy_text={"captions": {"tiktok": f"{title} #gta6", "facebook": "x"}},
                        updated_at=utcnow() - timedelta(minutes=minutes_ago))
        s.add(ec)
        s.commit()
        return ec.id


def test_clips_upload_evict_oldest_and_follow_deletes(syncer, fake, data_dir):
    if not shutil.which("ffmpeg"):
        pytest.skip("requer ffmpeg")
    old = _ready_clip(data_dir, "corte_velho", 30, 300_000)
    new = _ready_clip(data_dir, "corte_novo", 1, 300_000)
    syncer.max_bytes = 450_000  # cabe só um: o mais velho sai da nuvem (continua no PC)
    syncer.clips()
    assert set(fake.clips) >= {new} and old not in fake.clips
    row = fake.clips[new]
    assert row["output_path"].endswith(".mp4") and fake.objects[row["output_path"]] == b"\0" * 300_000
    thumb = fake.objects[row["cover_path"]]
    assert thumb[:2] == b"\xff\xd8" and len(thumb) < 30_000  # miniatura leve
    assert row["clip"]["copy_text"]["captions"] == {"tiktok": "corte_novo #gta6"}
    items = {it["clip"]["id"]: it for it in syncer.feed}
    assert items[new]["cloud"]["output"] == row["output_path"]
    assert items[old]["cloud"] is None and "só no PC" in items[old]["only_pc"]
    n_obj = len(fake.objects)
    assert syncer.clips()["uploaded"] == 0 and len(fake.objects) == n_obj  # não sobe de novo
    with session_scope() as s:  # apagou no PC → some da nuvem
        for cid in (old, new):
            s.delete(s.get(EditedClip, cid))
        s.commit()
    syncer.clips()
    assert new not in fake.clips and row["output_path"] not in fake.objects


def test_cloud_config_encrypts_key_and_never_returns_it(client, data_dir, monkeypatch):
    (data_dir / cloud.CONFIG_FILE).unlink(missing_ok=True)
    bad = client.post("/api/v1/cloud/config", headers=AUTH, json={"key": "abc"})
    assert bad.status_code == 422 and "SECRETA" in bad.json()["detail"]
    pub = client.post("/api/v1/cloud/config", headers=AUTH, json={"key": "sb_publishable_" + "y" * 30})
    assert pub.status_code == 422
    monkeypatch.setattr(cloud, "check_key", lambda url, key, transport=None: 0)
    r = client.post("/api/v1/cloud/config", headers=AUTH, json={"key": KEY, "app_url": "https://clipzou.vercel.app"})
    assert r.status_code == 200, r.text
    assert r.json()["configured"] and r.json()["app_url"] == "https://clipzou.vercel.app" and KEY not in r.text
    assert KEY not in (data_dir / cloud.CONFIG_FILE).read_text() and cloud.load_config()["key"] == KEY
    assert KEY not in client.get("/api/v1/cloud/status", headers=AUTH).text
    bad_link = client.post("/api/v1/cloud/config", headers=AUTH, json={"app_url": "javascript:alert(1)"})
    assert bad_link.status_code == 422
    assert client.delete("/api/v1/cloud/config", headers=AUTH).json()["configured"] is False
    assert cloud.load_config()["key"] == ""
