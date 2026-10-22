from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_llm_client
from app.core.config import Settings, get_settings
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "public" / "data" / "df_tabela_final.csv"
AMOSTRA_LINHAS = 5000


def _load_build_module():
    spec = importlib.util.spec_from_file_location("build_database", ROOT / "backend" / "scripts" / "build_database.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def amostra_csv(tmp_path_factory) -> Path:
    """As primeiras linhas do CSV real (alunos completos, ordenados por código)."""
    amostra = tmp_path_factory.mktemp("amostra") / "amostra.csv"
    with CSV.open(encoding="utf-8-sig") as src, amostra.open("w", encoding="utf-8") as dst:
        for i, linha in enumerate(src):
            if i > AMOSTRA_LINHAS:
                break
            dst.write(linha)
    return amostra


@pytest.fixture(scope="session")
def db_path(tmp_path_factory, amostra_csv) -> Path:
    """Banco gerado pelo script real a partir de uma amostra do CSV."""
    out = tmp_path_factory.mktemp("db") / "sigadash.db"
    _load_build_module().build(amostra_csv, out)
    return out


@pytest.fixture
def settings(db_path) -> Settings:
    return Settings(_env_file=None, openai_api_key="test", database_path=db_path)


class FakeLLM:
    """Devolve respostas pré-programadas, na ordem, e registra as chamadas."""

    def __init__(self, respostas: list[str | dict]) -> None:
        self.respostas = [json.dumps(r) if isinstance(r, dict) else r for r in respostas]
        self.chamadas: list[dict] = []

    def complete(self, system, messages, json_mode=False):
        self.chamadas.append({"system": system, "messages": messages, "json_mode": json_mode})
        return self.respostas.pop(0)


@pytest.fixture
def make_client(settings):
    def _make(llm: FakeLLM | None, settings_override: Settings | None = None) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings_override or settings
        if llm is not None:
            app.dependency_overrides[get_llm_client] = lambda: llm
        return TestClient(app)

    return _make
