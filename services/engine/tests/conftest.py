import os
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="stark_test_"))
os.environ.update(STARK_DATA_DIR=str(_TMP), STARK_API_TOKEN="test-token", STARK_WHISPER_MODEL="base",
                  STARK_LANGUAGE="pt", STARK_HWACCEL="none")
os.environ.pop("STARK_DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402

from stark_engine.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def data_dir() -> Path:
    return _TMP


def words_from(text_blocks: list[tuple[float, str]], wps: float = 2.6) -> list:
    """Gera palavras sintéticas [s, e, w, p] a partir de blocos (início, texto)."""
    out = []
    for start, text in text_blocks:
        t = start
        for w in text.split():
            out.append([round(t, 2), round(t + 0.8 / wps * 2, 2), w, 0.9])
            t += 1 / wps
    return out
