"""YouTube: metadados via oEmbed e feed RSS público (sem chave) e YouTube Data API v3 (chave). NÃO baixa vídeos.

Link do YouTube != autorização. Para editar, envie o arquivo original (ex.: seu vídeo via YouTube Studio)
com registro de direitos. Hosts fixos (anti-SSRF): o app nunca busca URL arbitrária do usuário.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import httpx

from .config import get_settings

HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
API = "https://www.googleapis.com/youtube/v3"
FEED = "https://www.youtube.com/feeds/videos.xml"
CHANNEL_RE = re.compile(r"(?<![A-Za-z0-9_-])UC[A-Za-z0-9_-]{22}(?![A-Za-z0-9_-])")
_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
       "m": "http://search.yahoo.com/mrss/"}
_UA = {"User-Agent": "Mozilla/5.0 (Clipzou; uso pessoal)"}


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


def live_search(q: str, max_results: int = 15, region: str = "BR") -> list[dict]:
    """Lives do YouTube agora (oficial), com espectadores simultâneos."""
    r = httpx.get(f"{API}/search", timeout=20, params={
        "part": "snippet", "type": "video", "eventType": "live", "q": q[:200], "maxResults": min(50, max_results),
        "order": "viewCount", "regionCode": region, "key": _key()})
    if r.status_code == 403:
        raise YouTubeError("cota da YouTube Data API esgotada ou chave inválida")
    r.raise_for_status()
    ids = [it["id"]["videoId"] for it in r.json().get("items", []) if it["id"].get("videoId")]
    if not ids:
        return []
    d = httpx.get(f"{API}/videos", timeout=20, params={"part": "snippet,liveStreamingDetails", "id": ",".join(ids),
                                                       "key": _key()})
    d.raise_for_status()
    out = []
    for it in d.json().get("items", []):
        sn, lv = it["snippet"], it.get("liveStreamingDetails", {})
        out.append({"platform": "youtube", "channel": sn["channelTitle"], "display_name": sn["channelTitle"],
                    "title": sn["title"], "viewers": int(lv.get("concurrentViewers", 0) or 0), "game": "",
                    "language": sn.get("defaultAudioLanguage", ""),
                    "thumbnail_url": sn["thumbnails"].get("medium", sn["thumbnails"]["default"])["url"],
                    "started_at": lv.get("actualStartTime"), "url": f"https://www.youtube.com/watch?v={it['id']}"})
    return out


# ------------------------------------------------------------------ feed RSS público (sem chave)
def channel_id(value: str) -> str:
    """'UC…' ou link youtube.com/channel/UC… → ID do canal."""
    m = CHANNEL_RE.search(value.strip())
    if not m:
        raise YouTubeError(f"canal inválido: {value[:60]} (use o ID UC… ou o link youtube.com/channel/UC…)")
    return m.group(0)


def _int(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def parse_feed(xml: bytes) -> list[dict]:
    """Lê o Atom do YouTube (título, canal, data, miniatura, views e likes)."""
    if len(xml) > 3_000_000 or b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
        raise YouTubeError("feed inesperado")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise YouTubeError("feed inválido") from e
    out = []
    for e in root.findall("a:entry", _NS):
        vid = e.findtext("yt:videoId", "", _NS)
        if not ID_RE.match(vid):
            continue
        link = e.find("a:link", _NS)
        href = link.get("href", "") if link is not None else ""
        g = e.find("m:group", _NS)
        thumb = g.find("m:thumbnail", _NS) if g is not None else None
        stats = g.find("m:community/m:statistics", _NS) if g is not None else None
        rating = g.find("m:community/m:starRating", _NS) if g is not None else None
        out.append({
            "youtube_id": vid, "title": e.findtext("a:title", "", _NS),
            "channel": e.findtext("a:author/a:name", "", _NS), "channel_id": e.findtext("yt:channelId", "", _NS),
            "published_at": e.findtext("a:published", "", _NS),
            "thumbnail_url": thumb.get("url") if thumb is not None else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "views": _int(stats.get("views") if stats is not None else 0),
            "likes": _int(rating.get("count") if rating is not None else 0),
            "short": "/shorts/" in href,
            "url": href if href.startswith("https://www.youtube.com/") else f"https://www.youtube.com/watch?v={vid}",
        })
    return out


def channel_feed(cid: str) -> list[dict]:
    """Últimos ~15 vídeos do canal pelo feed RSS público oficial (sem chave, sem baixar vídeo)."""
    if not CHANNEL_RE.fullmatch(cid):
        raise YouTubeError("ID de canal inválido")
    try:
        r = httpx.get(FEED, params={"channel_id": cid}, headers=_UA, timeout=15)
    except httpx.HTTPError as e:
        raise YouTubeError(f"feed indisponível: {type(e).__name__}") from e
    if r.status_code != 200:
        raise YouTubeError(f"feed indisponível ({r.status_code})")
    return parse_feed(r.content)


def channel_feeds(ids: list[str]) -> tuple[list[dict], int]:
    """Vários canais em paralelo. Retorna (vídeos, nº de canais que responderam)."""
    def one(cid: str) -> list[dict] | None:
        try:
            return channel_feed(cid)
        except YouTubeError:
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(one, ids[:50]))
    return [v for r in res if r for v in r], sum(r is not None for r in res)
