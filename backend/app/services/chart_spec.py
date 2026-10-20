"""Gráfico da resposta do chat: valida a sugestão do LLM e, sem ela, aplica uma regra fixa.

O gráfico só aponta colunas do resultado (nunca números): os valores
desenhados no frontend saem de `dados`, que vêm do SQL.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.schemas.chat import GraficoSpec

MAX_CATEGORIAS_REGRA = 15  # a regra fixa só desenha barras com até 15 categorias
RAZAO_MAX_ESCALA = 10      # séries juntas precisam ter ordem de grandeza parecida (um único eixo Y)
ROTULO_LONGO = 14          # categorias com rótulo maior que isso viram barra horizontal

_PERIODO_RE = re.compile(r"^\d{4}\.\d$")
_COLUNAS_ID = {"id", "codigo_estudante"}
_METRICA_PRINCIPAL_RE = re.compile(r"taxa|pct|percent|media|média")


def _valores(dados: list[list[Any]], i: int) -> list[Any]:
    return [linha[i] for linha in dados if i < len(linha) and linha[i] is not None]


def classificar_colunas(colunas: list[str], dados: list[list[Any]]) -> dict[str, str]:
    """'temporal' | 'numerica' | 'categorica' para cada coluna."""
    tipos: dict[str, str] = {}
    for i, nome in enumerate(colunas):
        vals = _valores(dados, i)
        if "periodo" in nome.lower() or (vals and all(isinstance(v, str) and _PERIODO_RE.match(v) for v in vals)):
            tipos[nome] = "temporal"
        elif (
            vals
            and nome.lower() not in _COLUNAS_ID
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals)
        ):
            tipos[nome] = "numerica"
        else:
            tipos[nome] = "categorica"
    return tipos


def _maximo_abs(colunas: list[str], dados: list[list[Any]], nome: str) -> float:
    vals = _valores(dados, colunas.index(nome))
    return max((abs(v) for v in vals), default=0.0)


def _mesma_escala(colunas: list[str], dados: list[list[Any]], ys: list[str]) -> bool:
    maximos = [_maximo_abs(colunas, dados, y) for y in ys]
    if max(maximos) == 0:
        return True
    if min(maximos) == 0:
        return False
    return max(maximos) / min(maximos) <= RAZAO_MAX_ESCALA


def validar_grafico(sugestao: Any, colunas: list[str], dados: list[list[Any]]) -> GraficoSpec | None:
    """Devolve a sugestão do LLM se ela for desenhável com estes dados; senão None."""
    if not isinstance(sugestao, dict) or len(dados) < 2:
        return None
    try:
        spec = GraficoSpec.model_validate(sugestao)
    except ValidationError:
        return None

    tipos = classificar_colunas(colunas, dados)
    if spec.x not in tipos or spec.x in spec.y or len(set(spec.y)) != len(spec.y):
        return None
    if any(tipos.get(y) != "numerica" for y in spec.y):
        return None
    if spec.tipo == "linha" and tipos[spec.x] != "temporal":
        return None
    if len(spec.y) > 1 and not _mesma_escala(colunas, dados, spec.y):
        return None
    if spec.tipo == "barra" and tipos[spec.x] == "categorica" and _rotulo_longo(colunas, dados, spec.x):
        # nomes longos (cursos, disciplinas) se sobrepõem no eixo X de barras verticais
        spec = spec.model_copy(update={"tipo": "barra_horizontal"})
    return spec


def _rotulo_longo(colunas: list[str], dados: list[list[Any]], coluna: str) -> bool:
    rotulos = [str(v) for v in _valores(dados, colunas.index(coluna))]
    return max(map(len, rotulos), default=0) > ROTULO_LONGO


def _titulo(y: str, x: str) -> str:
    def humano(nome: str) -> str:
        txt = nome.replace("_pct", " (%)").replace("_", " ").strip()
        return txt[:1].upper() + txt[1:]

    return f"{humano(y)} por {humano(x).lower()}"


def _metrica_principal(numericas: list[str]) -> str:
    for nome in numericas:
        if _METRICA_PRINCIPAL_RE.search(nome.lower()):
            return nome
    return numericas[-1]


def grafico_por_regra(colunas: list[str], dados: list[list[Any]]) -> GraficoSpec | None:
    """Regra fixa e conservadora: só série temporal ou ranking curto, com uma métrica."""
    if len(dados) < 2:
        return None
    tipos = classificar_colunas(colunas, dados)
    numericas = [c for c in colunas if tipos[c] == "numerica"]
    if not numericas:
        return None
    y = _metrica_principal(numericas)

    temporal = next((c for c in colunas if tipos[c] == "temporal"), None)
    if temporal:
        return GraficoSpec(tipo="linha", x=temporal, y=[y], titulo=_titulo(y, temporal))

    categorica = next((c for c in colunas if tipos[c] == "categorica"), None)
    if categorica and len(dados) <= MAX_CATEGORIAS_REGRA:
        tipo = "barra_horizontal" if _rotulo_longo(colunas, dados, categorica) else "barra"
        return GraficoSpec(tipo=tipo, x=categorica, y=[y], titulo=_titulo(y, categorica))
    return None


def escolher_grafico(sugestao: Any, colunas: list[str], dados: list[list[Any]]) -> tuple[GraficoSpec | None, str]:
    """Sugestão do LLM validada; se não houver ou for inválida, a regra fixa. Devolve (spec, origem)."""
    spec = validar_grafico(sugestao, colunas, dados)
    if spec:
        return spec, "modelo"
    spec = grafico_por_regra(colunas, dados)
    return (spec, "regra") if spec else (None, "nenhum")
