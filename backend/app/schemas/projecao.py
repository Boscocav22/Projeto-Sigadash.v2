from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LinhaProjecao(BaseModel):
    curso: str
    periodo_base: str
    periodo_alvo: str
    situacao: str  # "ALUNOS ATIVOS" | "ALUNOS RETIDOS" | "EVASÃO" | "CONCLUSÃO"
    quantidade: int
    proporcao: float


class ErroCurso(BaseModel):
    curso: str
    erro: str


class ProjecaoResponse(BaseModel):
    status: Literal["processando", "pronto", "erro", "desativado"]
    mensagem: str | None = None
    origem: Literal["cache", "calculo"] | None = None
    periodo_alvo: str | None = None
    periodos_ignorados: list[str] = Field(default_factory=list)
    gerado_em: str | None = None
    duracao_s: float | None = None
    linhas: list[LinhaProjecao] = Field(default_factory=list)
    erros: list[ErroCurso] = Field(default_factory=list)
