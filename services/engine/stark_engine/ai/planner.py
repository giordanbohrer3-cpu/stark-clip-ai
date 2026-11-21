"""Planejamento de cortes por IA (resposta JSON estruturada) + requisição para Modo Operador.

A IA só escolhe intervalos por ÍNDICE de frase -> cortes sempre caem em limites de frase reais.
Score final = média entre heurística explicável e nota da IA. Falha -> heurística.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from ..clipper import ClipAnalyzer, Window
from ..models import Workspace
from .providers import AIError, call_json, route

SYSTEM = ("Você é editor-chefe de cortes virais para TikTok/Reels/Shorts em PT-BR. Escolha trechos que funcionam "
          "sozinhos: gancho nos 3 primeiros segundos, desenvolvimento claro e conclusão. Não invente conteúdo. "
          "Responda SOMENTE JSON válido.")

SCHEMA = {
    "cuts": [{"start_idx": "int (frase inicial)", "end_idx": "int (frase final, inclusiva)",
              "title": "str <=70 chars, sem clickbait enganoso", "summary": "str <=180", "justification": "str",
              "hook_score": "int 0-100"}]
}


def sentence_listing(an: ClipAnalyzer, windows: list[Window] | None = None, max_chars: int = 18000) -> str:
    sents = an.sents
    full = "\n".join(f"[{s.idx}] {s.start:.1f}-{s.end:.1f}s {s.text}" for s in sents)
    if len(full) <= max_chars or not windows:
        return full
    keep: set[int] = set()
    for w in windows[:15]:  # transcrição longa: envia só regiões promissoras (+contexto)
        keep.update(range(max(0, w.i - 2), min(len(sents), w.j + 3)))
    return "\n".join(f"[{s.idx}] {s.start:.1f}-{s.end:.1f}s {s.text}" for s in sents if s.idx in keep)


def build_prompt(an: ClipAnalyzer, hints: list[Window], target: int) -> str:
    hint_txt = "\n".join(f"- frases {w.i}-{w.j} ({w.duration:.0f}s) score {w.score}" for w in hints[:8])
    return (
        f"Duração permitida por corte: {an.lo:.0f}-{an.hi:.0f}s (ideal ~{an.ideal:.0f}s).\n"
        f"Escolha até {target} cortes NÃO sobrepostos e NÃO redundantes. Se não houver conteúdo bom, devolva menos.\n"
        f"Candidatos da heurística (opcional usar):\n{hint_txt}\n\nFrases [índice] início-fim texto:\n"
        f"{sentence_listing(an, hints)}\n\nFormato JSON: {json.dumps(SCHEMA, ensure_ascii=False)}"
    )


def apply_cuts(an: ClipAnalyzer, cuts: list[dict], target: int, source: str) -> list[tuple[Window, dict]]:
    """Valida cortes vindos da IA/operador: índices, duração, sobreposição."""
    out: list[tuple[Window, dict]] = []
    n = len(an.sents)
    for c in cuts:
        try:
            i, j = int(c["start_idx"]), int(c["end_idx"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= i <= j < n):
            continue
        w = an.window(i, j)
        if w.duration < an.lo * 0.8 or w.duration > an.hi * 1.2:
            continue
        if any(w.start < o.end and o.start < w.end for o, _ in out):
            continue
        hook = max(0, min(100, int(c.get("hook_score", w.score))))
        w.score = round(0.5 * w.score + 0.5 * hook, 1)
        w.features["ai_hook"] = hook
        meta = {k: str(c.get(k, ""))[:300] for k in ("title", "summary", "justification")}
        meta["source"] = source
        out.append((w, meta))
        if len(out) == target:
            break
    return out


def llm_plan(session: Session, ws: Workspace, an: ClipAnalyzer, hints: list[Window], target: int):
    errors = []
    for provider in route(ws, "cut_planning"):
        try:
            data = call_json(session, ws, provider, "cut_planning", SYSTEM, build_prompt(an, hints, target), 1800)
            res = apply_cuts(an, data.get("cuts", []), target, f"llm:{provider}")
            if res:
                return res
            errors.append(f"{provider}: cortes inválidos")
        except AIError as e:
            errors.append(str(e))
    raise AIError("; ".join(errors) or "nenhum provedor habilitado")


def operator_request(an: ClipAnalyzer, hints: list[Window], target: int, video_id: int) -> str:
    """Markdown p/ Modo Operador: Claude Code/Gemini CLI/Codex (sua assinatura, uso interativo) responde o JSON."""
    return (
        f"# STARK CLIP AI — pedido de planejamento de cortes (vídeo {video_id})\n\n{SYSTEM}\n\n"
        f"{build_prompt(an, hints, target)}\n\n"
        f"Envie o JSON para: POST /api/v1/videos/{video_id}/cuts/import\n"
    )
