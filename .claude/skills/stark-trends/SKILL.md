---
name: stark-trends
description: Pesquisa tendências (temas, hashtags, áudios, formatos) só em fontes oficiais/autorizadas e registra no Radar. Use ao buscar o que está bombando num nicho.
---

# stark-trends

1. Fontes: YouTube Data API (`POST $API/trends/youtube?region=BR`), MCP vidIQ se conectado (ex.: tiktok_trending_sound_search, outliers — gasta créditos), e o que o usuário viu no TikTok Creative Center / Google Trends.
2. NÃO faça scraping. Registre cada sinal com fonte, data e confiança: `POST $API/trends` `{"kind":"hashtag|audio|topic|format","label":"…","url":"…","confidence":0.0-1.0,"license_note":"…"}`.
3. Áudio em alta: só usar pela biblioteca da própria plataforma ao postar (licença).
4. Gere ideias: `POST $API/trends/ideas {"niche":"…","topics":[…]}` e filtre hashtags irrelevantes.
