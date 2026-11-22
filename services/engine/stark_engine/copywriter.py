"""Títulos, legendas por rede e hashtags. Heurística local; IA opcional (modelo econômico)."""
from __future__ import annotations

import re
from collections import Counter

from sqlmodel import Session

from .ai.providers import AIError, call_json, route
from .clipper import content_words, norm, strip_accents
from .models import Workspace

RULES = {
    "tiktok": {"tags": 4, "max": 2200, "cta": "Comenta o que você acha 👇"},
    "instagram": {"tags": 5, "max": 2200, "cta": "Salva pra rever e manda pra quem precisa ver isso."},
    "facebook": {"tags": 3, "max": 5000, "cta": "Concorda? Conta nos comentários."},
    "youtube": {"tags": 3, "max": 5000, "cta": "Inscreva-se para mais cortes."},
}


BROAD = {"tiktok": "#fyp", "instagram": "#reels", "facebook": "#reels", "youtube": "#shorts"}
# palavras de conversa que viram # sem sentido ("#sabe", "#olha") e palavrões: nunca viram hashtag
FILLER = {
    "sabe", "olha", "olhe", "dessas", "desses", "dessa", "desse", "nessa", "nesse", "pessoal", "galera", "mano", "véi",
    "segunda", "primeira", "primeiro", "terceira", "importante", "ouviu", "ouvir", "falar", "falou", "fala", "disse",
    "dizer", "chegou", "chegar", "estou", "estamos", "estar", "ficou", "ficar", "deixa", "deixar", "pegar", "pegou",
    "queria", "quero", "precisa", "mesmo", "mesma", "outro", "outra", "outros", "outras", "nada", "algum", "alguma",
    "nenhum", "cada", "muitos", "muitas", "pouco", "dele", "dela", "deles", "delas", "nosso", "nossa", "certo",
    "verdade", "exemplo", "momento", "parte", "jeito", "forma", "beleza", "obrigado", "valeu", "realmente", "achei",
    "acha", "achou", "vendo", "viu", "vejo", "veio", "vindo", "indo", "saber", "sabia", "lembra", "entendeu", "pronto",
    "porra", "caralho", "merda", "foda", "fodase", "puta", "bosta", "cacete", "desgraça", "desgraca", "otario",
}


def to_tag(word: str) -> str:
    return "#" + re.sub(r"[^a-z0-9]", "", strip_accents(word).lower())


def niche_hashtags(niche: str) -> list[str]:
    """# fixas do nicho: GTA VI → #gta6 #gtavi #gta. Outros nichos: o próprio nome."""
    words = re.sub(r"[^a-z0-9 ]", " ", strip_accents(niche or "").lower()).split()
    if "gta" in words or " ".join(words).startswith("grand theft auto"):
        if any(w in ("vi", "6") for w in words):
            return ["#gta6", "#gtavi", "#gta"]
        return ["#gta5", "#gta"] if any(w in ("v", "5") for w in words) else ["#gta"]
    tag = to_tag(niche) if niche else ""
    return [tag] if 4 <= len(tag) <= 30 else []


def content_tags(text: str, keywords: list[str]) -> list[str]:
    """# do assunto do corte: só palavra que se repete (1 vez só costuma ser erro da transcrição)."""
    counts = Counter(strip_accents(w) for w in content_words(text))
    out = []
    for k in [*keywords, *counts]:
        w = strip_accents(norm(str(k)))
        if len(w) >= 4 and w not in FILLER and counts.get(w, 0) >= 2 and not w.isdigit():
            out.append(to_tag(w))
    return list(dict.fromkeys(out))


def heuristic_copy(title: str, text: str, keywords: list[str], niche_tags: list[str] | None = None) -> dict:
    niche = [t if t.startswith("#") else to_tag(t) for t in (niche_tags or [])]
    content = content_tags(text, keywords or [])
    caps, tags = {}, {}
    for p, r in RULES.items():
        pool = list(dict.fromkeys([*niche[:2], *content[:2], *niche[2:], *content[2:]]))
        pool = [t for t in pool if len(t) > 3][: max(0, r["tags"] - 1)]
        tags[p] = list(dict.fromkeys([*pool, BROAD[p]]))  # sempre 1 # de alcance no fim
        body = f"{title}\n\n{r['cta']}\n\n{' '.join(tags[p])}"
        caps[p] = body[: r["max"]]
    return {"title": title[:100], "captions": caps, "hashtags": tags, "source": "heuristic"}


SYSTEM = ("Você escreve legendas para TikTok, Instagram Reels, Facebook e YouTube Shorts em PT-BR. Sem promessas falsas, "
          "sem clickbait enganoso, sem hashtags irrelevantes. Responda SOMENTE JSON.")


def generate_copy(session: Session, ws: Workspace, title: str, text: str, keywords: list[str],
                  niche: str = "", niche_tags: list[str] | None = None) -> dict:
    niche = niche or str(((ws.settings or {}).get("radar") or {}).get("game") or "Grand Theft Auto VI")
    base = heuristic_copy(title, text, keywords, niche_tags or niche_hashtags(niche))
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
