"""Títulos, legendas por rede e hashtags. Heurística local; IA opcional (modelo econômico)."""
from __future__ import annotations

import re

from sqlmodel import Session

from .ai.providers import AIError, call_json, route
from .clipper import content_words, strip_accents
from .models import Workspace

RULES = {
    "tiktok": {"tags": 4, "max": 2200, "cta": "Comenta o que você acha 👇"},
    "instagram": {"tags": 5, "max": 2200, "cta": "Salva pra rever e manda pra quem precisa ver isso."},
    "facebook": {"tags": 3, "max": 5000, "cta": "Concorda? Conta nos comentários."},
    "youtube": {"tags": 3, "max": 5000, "cta": "Inscreva-se para mais cortes."},
}


def to_tag(word: str) -> str:
    return "#" + re.sub(r"[^a-z0-9]", "", strip_accents(word).lower())


def heuristic_copy(title: str, text: str, keywords: list[str], niche_tags: list[str] | None = None) -> dict:
    kws = keywords or [w for w in dict.fromkeys(content_words(text))][:6]
    niche = [t if t.startswith("#") else to_tag(t) for t in (niche_tags or [])]
    content = [to_tag(k) for k in kws if len(k) >= 4]
    tags_all = list(dict.fromkeys([*niche[:2], *content, *niche[2:]]))
    tags_all = [t for t in tags_all if len(t) > 3]
    caps, tags = {}, {}
    for p, r in RULES.items():
        tags[p] = tags_all[: r["tags"]]
        body = f"{title}\n\n{r['cta']}\n\n{' '.join(tags[p])}"
        caps[p] = body[: r["max"]]
    return {"title": title[:100], "captions": caps, "hashtags": tags, "source": "heuristic"}


SYSTEM = ("Você escreve legendas para TikTok, Instagram Reels, Facebook e YouTube Shorts em PT-BR. Sem promessas falsas, "
          "sem clickbait enganoso, sem hashtags irrelevantes. Responda SOMENTE JSON.")


def generate_copy(session: Session, ws: Workspace, title: str, text: str, keywords: list[str],
                  niche: str = "", niche_tags: list[str] | None = None) -> dict:
    base = heuristic_copy(title, text, keywords, niche_tags)
    prompt = (f"Nicho: {niche or 'geral'}\nTítulo sugerido: {title}\nTranscrição do corte:\n{text[:3500]}\n\n"
              'JSON: {"title": str<=80, "captions": {"tiktok": str, "instagram": str, "facebook": str, "youtube": str}, '
              '"hashtags": [str] (máx 6, pertinentes ao conteúdo)}')
    for provider in route(ws, "copywriting"):
        try:
            d = call_json(session, ws, provider, "copywriting", SYSTEM, prompt, 900)
            tags = [t if str(t).startswith("#") else to_tag(str(t)) for t in d.get("hashtags", [])][:6]
            caps = {p: str(d.get("captions", {}).get(p) or base["captions"][p])[: RULES[p]["max"]] for p in RULES}
            return {"title": str(d.get("title") or title)[:100], "captions": caps,
                    "hashtags": {p: tags[: RULES[p]["tags"]] or base["hashtags"][p] for p in RULES},
                    "source": f"llm:{provider}"}
        except AIError:
            continue
    return base
