"""Configuração da API, lida de variáveis de ambiente (ou do arquivo backend/.env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openai_api_key: str | None = None
    openai_base_url: str | None = None  # opcional: provedor compatível com a API da OpenAI
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 60.0

    # Banco consultado pelo chat (gerado por scripts/build_database.py)
    database_path: Path = BACKEND_DIR / "data" / "sigadash.db"

    # Limites da consulta
    max_linhas_resposta: int = 200   # linhas devolvidas ao frontend
    max_linhas_contexto: int = 40    # linhas enviadas ao LLM para redigir a resposta
    sql_timeout_s: float = 5.0
    max_tentativas_sql: int = 2      # gera + 1 correção a partir do erro
    max_historico: int = 6           # mensagens anteriores usadas como contexto

    # Origens separadas por vírgula; "*" libera todas.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
