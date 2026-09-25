"""
alunos_mining.py — regra de negócio do domínio "Alunos".

Python NÃO conhece a seleção atual do usuário (períodos marcados, indicador).
Por isso este módulo nunca pré-agrega por seleção: ele expõe o grão mais fino
útil — uma linha por (aluno, período) — e o TypeScript filtra/conta.

Saídas:
  alunos_periodo  -> [{codigo_estudante, curso, periodo, semestre, categoria}]
  alunos_resumo   -> [{codigo_estudante, curso, admissao, periodo_atual,
                       semestre_atual, situacao_atual, evasao, formacao}]
  alunos_filtros  -> {cursos: [...], periodos: [...]}

Regras:
  * Categoria de cada (aluno, período) pela prioridade
        FORMADO > EVADIDO > RETIDO > ATIVO
    sobre as situações (DS_TP_SIT_ACAD) observadas naquele período.
  * Regra dos 13 semestres: um período ATIVO cujo semestre BRUTO (sem piso)
    passa de LIMITE_SEMESTRES é rebaixado para RETIDO.
  * Para exibição, semestre recebe piso 1 (casos de admissão registrada depois
    do primeiro histórico).
  * Evasão = primeiro período EVADIDO (período, semestre, tipo bruto de saída).
  * Formação = período/semestre do último período ATIVO/RETIDO antes do
    primeiro FORMADO (se não houver, usa o próprio período do FORMADO).
  * alunos_resumo.situacao_atual = categoria do período MAIS RECENTE do aluno
    no CSV inteiro. É isso que "Todos os Períodos" significa no dashboard.
"""

from __future__ import annotations

import sys
from typing import Any

import pandas as pd

from common import (
    COL_ADMISSAO,
    COL_CURSO,
    COL_ESTUDANTE,
    COL_PERIODO,
    COL_SIT_ACAD,
    normalize_text,
    parse_period,
    period_key,
    semestres_cursados,
    sort_periods,
)

# Parâmetros de negócio
LIMITE_SEMESTRES = 13  # semestre bruto > 13 com situação ativa => RETIDO
PISO_SEMESTRE = 1

ATIVO, EVADIDO, RETIDO, FORMADO = "ATIVO", "EVADIDO", "RETIDO", "FORMADO"

# Prioridade entre as situações de base observadas num mesmo período.
PRIORIDADE = {ATIVO: 1, EVADIDO: 2, FORMADO: 3}
POR_PRIORIDADE = {v: k for k, v in PRIORIDADE.items()}

# Mapeamento DS_TP_SIT_ACAD (normalizado, sem acento)
SITUACOES_FORMADO = {"FORMADO"}
SITUACOES_EVADIDO = {
    "EXCLUIDO",
    "DESVINCULADO",
    "DESLIGAMENTO",
    "TRANSFERENCIA EXTERNA",
    "TRANSFERENCIA INTERNA",
}
SITUACOES_ATIVO = {
    "MATRICULADO",
    "MATRICULA VINCULO",
    "TRANCAMENTO",
    "INTERCAMBIO",
    "REINTEGRACAO",
    "MOBILIDADE ESTUDANTIL",
    "INTEGRALIZADO",
}


def _categoria_base(sit_norm: str | None) -> str:
    if sit_norm in SITUACOES_FORMADO:
        return FORMADO
    if sit_norm in SITUACOES_EVADIDO:
        return EVADIDO
    return ATIVO


def _log(msg: str) -> None:
    print(f"[alunos] {msg}", file=sys.stderr)

# Faz a mineração dos alunos, retornando um dicionário com a estrutura de dados compacta.
def mine_alunos(df: pd.DataFrame) -> dict[str, Any]:
    base = df[[COL_ESTUDANTE, COL_CURSO, COL_ADMISSAO, COL_SIT_ACAD, COL_PERIODO]].copy()

    # períodos inválidos ficam de fora (parse_period -> None)
    validos = base[COL_PERIODO].map(lambda p: parse_period(p) is not None)
    descartadas = int((~validos).sum())
    if descartadas:
        _log(f"{descartadas} linha(s) com período inválido descartada(s)")
    base = base[validos]

    # situação de base de cada linha
    sit_norm = base[COL_SIT_ACAD].map(normalize_text)
    conhecidas = SITUACOES_FORMADO | SITUACOES_EVADIDO | SITUACOES_ATIVO
    desconhecidas = sorted({s for s in sit_norm.dropna().unique() if s not in conhecidas})
    if desconhecidas:
        _log(f"situações não mapeadas (tratadas como ATIVO): {desconhecidas}")
    base["_cat"] = sit_norm.map(_categoria_base)
    base["_prio"] = base["_cat"].map(PRIORIDADE)

    # atributos fixos do aluno (curso e admissão são únicos por aluno no CSV)
    por_aluno = (
        base.groupby(COL_ESTUDANTE, sort=False)
        .agg(curso=(COL_CURSO, "first"), admissao=(COL_ADMISSAO, "first"))
    )

    # categoria de base por (aluno, período)
    grp = base.groupby([COL_ESTUDANTE, COL_PERIODO], sort=False)
    per = grp["_prio"].max().rename("_prio").reset_index()
    per["_cat"] = per["_prio"].map(POR_PRIORIDADE)

    # tipo bruto de saída (texto original do CSV) nos períodos com evasão
    ev = base[base["_cat"] == EVADIDO]
    tipos = (
        ev.sort_values(COL_SIT_ACAD)
        .groupby([COL_ESTUDANTE, COL_PERIODO], sort=False)[COL_SIT_ACAD]
        .first()
        .rename("_tipo")
        .reset_index()
    )
    per = per.merge(tipos, on=[COL_ESTUDANTE, COL_PERIODO], how="left")
    per = per.join(por_aluno, on=COL_ESTUDANTE)

    # semestre bruto (cache por par admissão/período)
    cache: dict[tuple[Any, Any], int | None] = {}

    def _sem(adm: Any, p: Any) -> int | None:
        k = (adm, p)
        if k not in cache:
            cache[k] = semestres_cursados(adm, p)
        return cache[k]

    per["_sem_bruto"] = [_sem(a, p) for a, p in zip(per["admissao"], per[COL_PERIODO])]

    # regra dos 13 semestres
    def _cat_final(cat: str, sem_bruto: int | None) -> str:
        if cat == ATIVO and sem_bruto is not None and sem_bruto > LIMITE_SEMESTRES:
            return RETIDO
        return cat

    per["categoria"] = [_cat_final(c, s) for c, s in zip(per["_cat"], per["_sem_bruto"])]

    sem_admissao = per["_sem_bruto"].isna()
    if sem_admissao.any():
        _log(
            f"{int(sem_admissao.sum())} linha(s) aluno×período sem admissão válida "
            "— semestre exibido como 1"
        )
    abaixo_piso = per["_sem_bruto"].notna() & (per["_sem_bruto"] < PISO_SEMESTRE)
    alunos_abaixo = per.loc[abaixo_piso, COL_ESTUDANTE].nunique()
    if alunos_abaixo:
        _log(f"{alunos_abaixo} aluno(s) com histórico anterior à admissão — piso de 1 semestre aplicado")

    per["semestre"] = [
        PISO_SEMESTRE if s is None or pd.isna(s) else max(PISO_SEMESTRE, int(s))
        for s in per["_sem_bruto"]
    ]

    # ordem cronológica dentro de cada aluno
    per["_k"] = per[COL_PERIODO].map(period_key)
    per = per.sort_values([COL_ESTUDANTE, "_k"], kind="stable").reset_index(drop=True)

    # alunos_periodo
    alunos_periodo = [
        {
            "codigo_estudante": str(e),
            "curso": c,
            "periodo": p,
            "semestre": int(s),
            "categoria": cat,
        }
        for e, c, p, s, cat in zip(
            per[COL_ESTUDANTE], per["curso"], per[COL_PERIODO], per["semestre"], per["categoria"]
        )
    ]

    # alunos_resumo
    alunos_resumo: list[dict[str, Any]] = []
    for est, g in per.groupby(COL_ESTUDANTE, sort=True):
        periodos = g[COL_PERIODO].tolist()
        cats = g["categoria"].tolist()
        sems = g["semestre"].tolist()
        tipos_saida = g["_tipo"].tolist()

        evasao = None
        for p, c, s, t in zip(periodos, cats, sems, tipos_saida):
            if c == EVADIDO:
                evasao = {
                    "periodo": p,
                    "semestre": int(s),
                    "tipo": t if isinstance(t, str) else "NÃO INFORMADO",
                }
                break

        formacao = None
        if FORMADO in cats:
            i_form = cats.index(FORMADO)
            i_ref = i_form
            for j in range(i_form - 1, -1, -1):
                if cats[j] in (ATIVO, RETIDO):
                    i_ref = j
                    break
            formacao = {"periodo": periodos[i_ref], "semestre": int(sems[i_ref])}

        adm = g["admissao"].iloc[0]
        alunos_resumo.append(
            {
                "codigo_estudante": str(est),
                "curso": g["curso"].iloc[0],
                "admissao": adm if isinstance(adm, str) else None,
                "periodo_atual": periodos[-1],
                "semestre_atual": int(sems[-1]),
                "situacao_atual": cats[-1],
                "evasao": evasao,
                "formacao": formacao,
            }
        )

    # alunos_filtros
    cursos = sorted({c for c in per["curso"].dropna().unique()})
    alunos_filtros = {"cursos": cursos, "periodos": sort_periods(per[COL_PERIODO].unique())}

    _log(
        f"{len(alunos_resumo)} alunos, {len(alunos_periodo)} linhas aluno×período, "
        f"{len(cursos)} cursos, {len(alunos_filtros['periodos'])} períodos"
    )
    return {
        "alunos_periodo": alunos_periodo,
        "alunos_resumo": alunos_resumo,
        "alunos_filtros": alunos_filtros,
    }
