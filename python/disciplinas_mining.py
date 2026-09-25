"""
disciplinas_mining.py — regra de negócio do domínio "Disciplinas".

Resolve, linha a linha, o que o TypeScript não decide mais:
  * APROVADO ou DISPENSADO  -> aprovado = 1
  * REPROVADO               -> reprovado = 1
  * qualquer outra situação -> 0 / 0 (conta só como matrícula)

Formato colunar (compacto para ~380 mil matrículas):
  {
    "cursos":      [str, ...],
    "disciplinas": [str, ...],
    "periodos":    [str, ...],            # ordem cronológica
    "rows": [[cursoIdx, disciplinaIdx, periodoIdx,
              aprovado(0|1), reprovado(0|1), media|null, faltas|null], ...]
  }

"""

from __future__ import annotations

import math
import sys
from typing import Any

import pandas as pd

from common import (
    COL_CURSO,
    COL_DISCIPLINA,
    COL_FALTAS,
    COL_MEDIA,
    COL_PERIODO,
    COL_SIT_HIST,
    normalize_text,
    parse_period,
    sort_periods,
)

SITUACOES_APROVADO = {"APROVADO", "DISPENSADO"}
SITUACOES_REPROVADO = {"REPROVADO"}


def _log(msg: str) -> None:
    print(f"[disciplinas] {msg}", file=sys.stderr)


def _num(v: Any) -> float | int | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    f = round(float(v), 2)
    return int(f) if f.is_integer() else f

# Faz a mineração das disciplinas, retornando um dicionário com a estrutura de dados compacta.
def mine_disciplinas(df: pd.DataFrame) -> dict[str, Any]:
    base = df[[COL_CURSO, COL_DISCIPLINA, COL_PERIODO, COL_SIT_HIST, COL_MEDIA, COL_FALTAS]]

    ok = (
        base[COL_CURSO].notna()
        & base[COL_DISCIPLINA].notna()
        & base[COL_PERIODO].map(lambda p: parse_period(p) is not None)
    )
    descartadas = int((~ok).sum())
    if descartadas:
        _log(f"{descartadas} linha(s) sem curso/disciplina/período válido descartada(s)")
    base = base[ok]

    cursos = sorted(base[COL_CURSO].unique().tolist())
    disciplinas = sorted(base[COL_DISCIPLINA].unique().tolist())
    periodos = sort_periods(base[COL_PERIODO].unique())

    ci = {c: i for i, c in enumerate(cursos)}
    di = {d: i for i, d in enumerate(disciplinas)}
    pi = {p: i for i, p in enumerate(periodos)}

    sit = base[COL_SIT_HIST].map(normalize_text)
    aprov = sit.isin(SITUACOES_APROVADO).astype(int)
    reprov = sit.isin(SITUACOES_REPROVADO).astype(int)

    rows = [
        [ci[c], di[d], pi[p], int(a), int(r), _num(m), _num(f)]
        for c, d, p, a, r, m, f in zip(
            base[COL_CURSO],
            base[COL_DISCIPLINA],
            base[COL_PERIODO],
            aprov,
            reprov,
            base[COL_MEDIA],
            base[COL_FALTAS],
        )
    ]

    _log(
        f"{len(rows)} matrículas, {len(disciplinas)} disciplinas, {len(cursos)} cursos, "
        f"{len(periodos)} períodos | aprovadas={int(aprov.sum())} reprovadas={int(reprov.sum())}"
    )
    return {
        "disciplinas_rows": {
            "cursos": cursos,
            "disciplinas": disciplinas,
            "periodos": periodos,
            "rows": rows,
        }
    }
