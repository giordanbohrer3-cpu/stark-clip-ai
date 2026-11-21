"""YouTube: metadados via oEmbed (sem chave) e YouTube Data API v3 (chave). NÃO baixa vídeos.

Link do YouTube != autorização. Para editar, envie o arquivo original (ex.: seu vídeo via YouTube Studio)
com registro de direitos. Hosts fixos (anti-SSRF): o app nunca busca URL arbitrária do usuário.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import httpx

from .config import get_settings

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
API = "https://www.googleapis.com/youtube/v3"


class YouTubeError(ValueError):
    pass


def parse_id(url: str) -> str:
    u = urlparse(url.strip())
    if u.scheme not in ("http", "https") or (u.hostname or "").lower() not in HOSTS:
        raise YouTubeError("URL não é do YouTube")
    if u.hostname == "youtu.be":
        vid = u.path.strip("/").split("/")[0]
    elif u.path == "/watch":
        vid = parse_qs(u.query).get("v", [""])[0]
    else:
        parts = u.path.strip("/").split("/")
        vid = parts[1] if len(parts) > 1 and parts[0] in ("shorts", "live", "embed", "v") else ""
    if not ID_RE.match(vid):
        raise YouTubeError("ID de vídeo inválido")
    return vid


def oembed(video_id: str) -> dict:
    r = httpx.get("https://www.youtube.com/oembed", timeout=15, params={
        "url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"})
    if r.status_code != 200:
        raise YouTubeError("vídeo indisponível (privado/removido?)")
    d = r.json()
    return {"youtube_id": video_id, "title": d.get("title", ""), "channel": d.get("author_name", ""),
            "thumbnail_url": d.get("thumbnail_url"), "url": f"https://www.youtube.com/watch?v={video_id}"}


def iso_duration(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def _key() -> str:
    key = get_settings().youtube_api_key
    if not key:
        raise YouTubeError("defina STARK_YOUTUBE_API_KEY (YouTube Data API v3) para busca/tendências")
    return key


def _details(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    r = httpx.get(f"{API}/videos", timeout=20, params={
        "part": "snippet,contentDetails,statistics,status", "id": ",".join(ids), "key": _key()})
    r.raise_for_status()
    out = []
    for it in r.json().get("items", []):
        sn, st = it["snippet"], it.get("statistics", {})
        out.append({
            "youtube_id": it["id"], "title": sn["title"], "channel": sn["channelTitle"],
            "published_at": sn["publishedAt"], "thumbnail_url": sn["thumbnails"].get("high", sn["thumbnails"]["default"])["url"],
            "duration_s": iso_duration(it["contentDetails"]["duration"]), "views": int(st.get("viewCount", 0)),
            "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
            "license": it.get("status", {}).get("license", "youtube"), "tags": sn.get("tags", [])[:10],
            "url": f"https://www.youtube.com/watch?v={it['id']}",
        })
    return out


def search(q: str, max_results: int = 12, order: str = "relevance", region: str = "BR",
           published_after: str | None = None, channel_id: str | None = None) -> list[dict]:
    params = {"part": "snippet", "type": "video", "q": q[:200], "maxResults": min(25, max_results),
              "order": order if order in ("relevance", "viewCount", "date", "rating") else "relevance",
              "regionCode": region, "relevanceLanguage": "pt", "key": _key()}
    if published_after:
        params["publishedAfter"] = published_after
    if channel_id:
        params["channelId"] = channel_id
    r = httpx.get(f"{API}/search", timeout=20, params=params)
    if r.status_code == 403:
        raise YouTubeError("cota da YouTube Data API esgotada ou chave inválida")
    r.raise_for_status()
    return _details([it["id"]["videoId"] for it in r.json().get("items", []) if it["id"].get("videoId")])


def trending(region: str = "BR", category: str | None = None, max_results: int = 20) -> list[dict]:
    params = {"part": "id", "chart": "mostPopular", "regionCode": region, "maxResults": min(50, max_results),
              "key": _key()}
    if category:
        params["videoCategoryId"] = category
    r = httpx.get(f"{API}/videos", timeout=20, params=params)
    r.raise_for_status()
    return _details([it["id"] for it in r.json().get("items", [])])
