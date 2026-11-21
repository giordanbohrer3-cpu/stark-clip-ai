# Motor STARK (API + worker). Mesma imagem, comandos diferentes no compose.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project
COPY . .
RUN uv sync --no-dev

ENV PATH="/app/.venv/bin:$PATH" STARK_DATA_DIR=/data PYTHONUNBUFFERED=1
RUN useradd -m stark && mkdir -p /data && chown -R stark /data /app
USER stark
EXPOSE 8787
HEALTHCHECK --interval=15s --timeout=5s --retries=5 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health')" || exit 1
CMD ["uvicorn", "stark_engine.main:app", "--host", "0.0.0.0", "--port", "8787"]
