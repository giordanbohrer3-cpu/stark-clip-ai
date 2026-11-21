"""Orquestrador de IA: APIs oficiais (Anthropic, OpenAI, Gemini) e Ollama local.

Regras: pagos desativados por padrão; orçamento mensal com limite rígido checado ANTES da chamada;
uso registrado (AIUsage); retentativa em 429/5xx; nunca usa cookies/sessões web de assinaturas.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import func
from sqlmodel import Session, select

from ..config import get_settings
from ..models import AIUsage, Workspace, utcnow
from ..security import ws_settings

log = logging.getLogger(__name__)
PROVIDERS = ("ollama", "gemini", "anthropic", "openai")  # ordem 'auto': local/grátis primeiro


class AIError(RuntimeError):
    pass


class BudgetExceeded(AIError):
    pass


def _key(provider: str) -> str:
    return getattr(get_settings(), f"{provider}_api_key", "") if provider != "ollama" else "local"


def provider_status(ws: Workspace) -> list[dict]:
    cfg = ws_settings(ws)["ai"]["providers"]
    return [{"provider": p, "enabled": bool(cfg[p]["enabled"]), "has_key": bool(_key(p)), "model": cfg[p]["model"],
             "paid": p != "ollama", "price_in": cfg[p]["price_in"], "price_out": cfg[p]["price_out"]} for p in PROVIDERS]


def month_spend(session: Session, ws_id: int) -> float:
    now = utcnow()
    start = datetime(now.year, now.month, 1, tzinfo=UTC)
    total = session.exec(select(func.coalesce(func.sum(AIUsage.cost_usd), 0.0))
                         .where(AIUsage.workspace_id == ws_id, AIUsage.created_at >= start)).one()
    return float(total or 0)


def usable(ws: Workspace, provider: str) -> bool:
    cfg = ws_settings(ws)["ai"]["providers"].get(provider, {})
    return bool(cfg.get("enabled")) and bool(_key(provider))


def route(ws: Workspace, task: str) -> list[str]:
    choice = ws_settings(ws)["ai"]["routing"].get(task, "heuristic")
    if choice == "heuristic":
        return []
    order = list(PROVIDERS) if choice == "auto" else [choice]
    return [p for p in order if usable(ws, p)]


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise AIError("resposta sem JSON")
    return json.loads(m.group(0))


def _request(provider: str, model: str, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]:
    s, key = get_settings(), _key(provider)
    if provider == "anthropic":
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=120, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        text = "".join(b.get("text", "") for b in d.get("content", []))
        return text, d["usage"]["input_tokens"], d["usage"]["output_tokens"]
    if provider == "openai":
        r = httpx.post("https://api.openai.com/v1/chat/completions", timeout=120,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "response_format": {"type": "json_object"},
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        return d["choices"][0]["message"]["content"], d["usage"]["prompt_tokens"], d["usage"]["completion_tokens"]
    if provider == "gemini":
        r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                       timeout=120, headers={"x-goog-api-key": key},
                       json={"systemInstruction": {"parts": [{"text": system}]},
                             "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                             "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens}})
        r.raise_for_status()
        d = r.json()
        text = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
        u = d.get("usageMetadata", {})
        return text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0)
    if provider == "ollama":
        r = httpx.post(f"{s.ollama_url}/api/chat", timeout=600,
                       json={"model": model, "stream": False, "format": "json",
                             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
        r.raise_for_status()
        d = r.json()
        return d["message"]["content"], d.get("prompt_eval_count", 0), d.get("eval_count", 0)
    raise AIError(f"provedor desconhecido: {provider}")


def call_json(session: Session, ws: Workspace, provider: str, task: str, system: str, prompt: str,
              max_tokens: int = 1500) -> dict:
    ai = ws_settings(ws)["ai"]
    cfg = ai["providers"][provider]
    if not usable(ws, provider):
        raise AIError(f"{provider} desativado ou sem chave")
    est_in = (len(system) + len(prompt)) / 3.5
    est = (est_in * cfg["price_in"] + max_tokens * cfg["price_out"]) / 1e6
    if provider != "ollama" and ai["hard_limit"]:
        spent = month_spend(session, ws.id)
        if spent + est > float(ai["monthly_budget_usd"]):
            raise BudgetExceeded(f"orçamento mensal (US$ {ai['monthly_budget_usd']:.2f}) seria excedido")
    last_err = ""
    for attempt in range(3):
        try:
            text, tin, tout = _request(provider, cfg["model"], system, prompt, max_tokens)
            cost = (tin * cfg["price_in"] + tout * cfg["price_out"]) / 1e6
            session.add(AIUsage(workspace_id=ws.id, provider=provider, model=cfg["model"], task=task,
                                input_tokens=tin, output_tokens=tout, cost_usd=round(cost, 6)))
            session.commit()
            return _parse_json(text)
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            last_err = f"HTTP {code}"
            if code in (429, 500, 502, 503, 529) and attempt < 2:
                wait = float(e.response.headers.get("retry-after", 2 ** (attempt + 2)) or 4)
                time.sleep(min(wait, 30))
                continue
            break
        except (httpx.HTTPError, ValueError, KeyError, IndexError, AIError) as e:
            last_err = type(e).__name__ + ": " + str(e)[:200]
            break
    session.add(AIUsage(workspace_id=ws.id, provider=provider, model=cfg["model"], task=task, ok=False,
                        error=last_err))
    session.commit()
    raise AIError(f"{provider} falhou: {last_err}")
