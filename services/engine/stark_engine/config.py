"""Configuração via variáveis STARK_* (ou .env). Segredos ficam só no servidor."""
from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENGINE_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ENGINE_ROOT / "assets"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STARK_", env_file=".env", extra="ignore")

    data_dir: Path = ENGINE_ROOT / "data"
    database_url: str = ""  # vazio = SQLite em data_dir; prod: postgresql+psycopg://...
    api_token: str = ""  # vazio = gerado em data_dir/.api_token
    secret_key: str = ""  # Fernet p/ tokens OAuth; vazio = gerado em data_dir/.secret_key

    max_upload_mb: int = 4096
    max_duration_s: int = 4 * 3600
    allowed_ext: tuple[str, ...] = (".mp4", ".mov", ".mkv", ".webm", ".m4v")

    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute: str = "int8"
    language: str | None = None  # None = autodetect

    hwaccel: str = "auto"  # auto|none|nvenc
    youtube_api_key: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"

    worker_poll_s: float = 1.0
    lease_s: int = 120

    @property
    def db_url(self) -> str:
        return self.database_url or f"sqlite:///{(self.data_dir / 'stark.db').as_posix()}"

    def ensure_dirs(self) -> None:
        for sub in ("media", "clips", "exports", "cache", "branding", "tmp"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)

    def _file_secret(self, name: str, nbytes: int = 32) -> str:
        path = self.data_dir / name
        if path.exists():
            return path.read_text().strip()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(nbytes)
        path.write_text(value)
        path.chmod(0o600)
        return value

    def resolved_api_token(self) -> str:
        return self.api_token or self._file_secret(".api_token")

    def resolved_secret_key(self) -> str:
        return self.secret_key or self._file_secret(".secret_key")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir = s.data_dir.resolve()
    s.ensure_dirs()
    return s
