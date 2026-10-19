from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HistoricoItem(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    pergunta: str = Field(min_length=1, max_length=1000)
    historico: list[HistoricoItem] = Field(default_factory=list, max_length=20)


class GraficoSpec(BaseModel):
    """Como desenhar `dados`: só nomes de colunas, nunca valores."""

    tipo: Literal["barra", "barra_horizontal", "linha"]
    x: str
    y: list[str] = Field(min_length=1, max_length=3)
    titulo: str = Field(default="", max_length=100)


class ChatResponse(BaseModel):
    resposta: str
    sql: str | None = None
    colunas: list[str] = Field(default_factory=list)
    dados: list[list[Any]] = Field(default_factory=list)
    total_linhas: int = 0
    truncado: bool = False
    grafico: GraficoSpec | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degradado"]
    banco: bool
    llm_configurado: bool
