"""Download seguro de vídeos por link (campanhas de clipes, clipes Twitch autorizados).

Anti-SSRF: só https, resolve DNS e recusa IP privado/loopback/link-local em CADA redirecionamento.
Links de compartilhamento do Google Drive e Dropbox viram download direto. YouTube é recusado (Termos).
"""
from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import httpx

BLOCKED_HOSTS = ("youtube.com", "youtu.be", "www.youtube.com", "m.youtube.com")
MAX_REDIRECTS = 6


class ImportError_(ValueError):  # noqa: N801 - evita colisão com ImportError embutido
    pass


def normalize(url: str) -> str:
    u = urlparse(url.strip())
    host = (u.hostname or "").lower()
    if host in ("drive.google.com", "docs.google.com"):
        m = re.search(r"/d/([A-Za-z0-9_-]{10,})", u.path) or re.search(r"id=([A-Za-z0-9_-]{10,})", u.query)
        if m:
            return f"https://drive.usercontent.google.com/download?id={m.group(1)}&export=download&confirm=t"
    if host.endswith("dropbox.com"):
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        q["dl"] = "1"
        return urlunparse(u._replace(query=urlencode(q)))
    return url.strip()


def check_public(url: str) -> None:
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host:
        raise ImportError_("use um link https")
    if host in BLOCKED_HOSTS or host.endswith(".youtube.com"):
        raise ImportError_("YouTube não permite baixar vídeos (Termos). Peça o arquivo (Drive/Dropbox) ao dono")
    try:
        infos = socket.getaddrinfo(host, u.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ImportError_(f"endereço não encontrado: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            raise ImportError_("endereço interno bloqueado")


def download(url: str, dst: Path, limit_mb: int, on_progress=None, guard=check_public) -> int:
    """Baixa seguindo redirecionamentos validados. Retorna bytes gravados."""
    url = normalize(url)
    limit = limit_mb * 1024 * 1024
    with httpx.Client(timeout=httpx.Timeout(30, read=120), follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS):
            guard(url)
            with client.stream("GET", url, headers={"User-Agent": "STARK-CLIP-AI/1.0"}) as r:
                if r.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code != 200:
                    raise ImportError_(f"download recusado (HTTP {r.status_code}). Link é público?")
                ctype = r.headers.get("content-type", "")
                if "text/html" in ctype:
                    raise ImportError_("o link abriu uma página, não um arquivo de vídeo (deixe o arquivo público)")
                total = int(r.headers.get("content-length") or 0)
                if total and total > limit:
                    raise ImportError_(f"arquivo maior que {limit_mb} MB")
                size = 0
                dst.parent.mkdir(parents=True, exist_ok=True)
                with dst.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        size += len(chunk)
                        if size > limit:
                            raise ImportError_(f"arquivo maior que {limit_mb} MB")
                        f.write(chunk)
                        if on_progress and total:
                            on_progress(size / total)
                return size
    raise ImportError_("redirecionamentos demais")
