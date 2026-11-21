---
name: stark-costs
description: Controla custo de IA: orçamento mensal, limite rígido, roteamento (heurística/Ollama/Gemini/Claude/OpenAI) e consumo. Use antes de ativar APIs pagas ou ao revisar gastos.
---

# stark-costs

1. `API="http://127.0.0.1:8787/api/v1"; AUTH="Authorization: Bearer $(cat services/engine/data/.api_token)"`; estado: `GET $API/settings` e `GET $API/ai/usage`; painel: `GET $API/stats` (ai.month_spend_usd).
2. Ordem de custo: heurística local (0) → Ollama local (0) → Gemini API (free tier) → Claude Haiku / GPT mini.
3. Ativar pago exige `PATCH $API/settings?confirm_paid=true` + orçamento > 0. Nunca ative sem pedido explícito do usuário.
4. Assinaturas Claude/ChatGPT/Gemini não são API: para usá-las, Modo Operador (skill stark-cuts) no CLI oficial.
