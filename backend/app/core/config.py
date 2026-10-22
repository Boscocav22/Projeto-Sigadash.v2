"""Configuração da API, lida de variáveis de ambiente (ou do arquivo backend/.env)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent


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

    # Projeção (algoritmo do notebook regress_copy_6.ipynb), calculada ao iniciar a API
    projecao_ativa: bool = True
    projecao_csv_path: Path = ROOT_DIR / "public" / "data" / "df_tabela_final.csv"
    projecao_cache_path: Path = BACKEND_DIR / "data" / "projecao_cache.json"
    projecao_periodos_ignorados: str = "2025.1,2025.2"  # poucos alunos; fora do treino e da coorte-base

    # Origens separadas por vírgula; "*" libera todas.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("openai_api_key", "openai_base_url", mode="before")
    @classmethod
    def _vazio_vira_none(cls, v: object) -> object:
        # o docker compose passa "" quando a variável não foi definida no .env
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def projecao_periodos_ignorados_lista(self) -> list[str]:
        return [p.strip() for p in self.projecao_periodos_ignorados.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
