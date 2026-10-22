"""
Preparação de df_tabela_final.csv para o ClassificadorAcademico.

Porta as células 3 a 8 do notebook regress_copy_6.ipynb. A única mudança
pedida é a situação acadêmica (célula 4): em vez do mapa e da regra
"qtd_periodos > 12" do notebook, usa as mesmas categorias do dashboard
(python/alunos_mining.py): prioridade FORMADO > EVADIDO > ATIVO por
aluno×período e RETIDO para o período ATIVO com semestre bruto > 13.

O modo "notebook" mantém a célula 4 original; serve para validar que o
restante do algoritmo reproduz o resumo gerado pelo notebook.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import pandas as pd

# As regras de categoria vêm da mineração do dashboard (python/), para não duplicá-las.
_PYTHON_DIR = Path(__file__).resolve().parents[3] / "python"
if str(_PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(_PYTHON_DIR))

from alunos_mining import (  # noqa: E402
    ATIVO,
    EVADIDO,
    FORMADO,
    LIMITE_SEMESTRES,
    POR_PRIORIDADE,
    PRIORIDADE,
    RETIDO,
    _categoria_base,
)
from common import normalize_text, semestres_cursados  # noqa: E402

Categorias = Literal["dashboard", "notebook"]

# Rótulos que o ClassificadorAcademico espera (estados terminais e ingresso usam estes nomes).
ROTULO_DA_CATEGORIA = {
    ATIVO: "ALUNOS ATIVOS",
    RETIDO: "ALUNOS RETIDOS",
    EVADIDO: "EVASÃO",
    FORMADO: "CONCLUSÃO",
}

# Célula 4 original do notebook (só para o modo de validação).
_MAPA_NOTEBOOK = {
    "FORMADO": "CONCLUSÃO", "INTEGRALIZADO": "CONCLUSÃO", "EXCLUÍDO": "EVASÃO", "DESLIGAMENTO": "EVASÃO",
    "DESVINCULADO": "EVASÃO", "TRANSFERENCIA EXTERNA": "EVASÃO", "TRANSFERENCIA INTERNA": "EVASÃO",
    "TRANCAMENTO": "ALUNOS RETIDOS", "REINTEGRAÇÃO": "ALUNOS RETIDOS",
    "MOBILIDADE ESTUDANTIL": "ALUNOS ATIVOS", "INTERCAMBIO": "ALUNOS ATIVOS", "MATRICULADO SOB JUDICE": "ALUNOS ATIVOS",
    "MATRICULA VINCULO": "ALUNOS ATIVOS", "MATRICULADO": "ALUNOS ATIVOS",
}


# Célula 3 — converte "AAAA.S" em número sequencial de semestres.
# Como no notebook, 2020.3 vira 2020*2+3, o mesmo valor de 2021.1.
def para_semestre(p):
    ano, sem = str(p).split(".")
    return int(ano) * 2 + int(sem)  # cada ano = 2 semestres


def as_float(n):
    return float(n)


def _situacao_dashboard(copia: pd.DataFrame) -> pd.Series:
    """Categoria do dashboard por aluno×período, repetida em todas as linhas daquele período."""
    base = copia["DS_TP_SIT_ACAD"].map(normalize_text).map(_categoria_base)
    prioridade = base.map(PRIORIDADE)
    prioridade_periodo = prioridade.groupby(
        [copia["codigo_estudante"], copia["CD_PERD_LETV"]]
    ).transform("max")
    categoria = prioridade_periodo.map(POR_PRIORIDADE)

    pares = pd.Series(list(zip(copia["PERIODO_ADMIS"], copia["CD_PERD_LETV"])), index=copia.index)
    cache: dict = {}
    for par in pares.unique():
        adm, per = par
        cache[par] = None if pd.isna(adm) else semestres_cursados(adm, per)
    sem_bruto = pares.map(cache)

    # Regra dos 13 semestres do dashboard: período ATIVO com semestre bruto > 13 vira RETIDO.
    retido = (categoria == ATIVO) & sem_bruto.notna() & (sem_bruto.astype(float) > LIMITE_SEMESTRES)
    categoria = categoria.mask(retido, RETIDO)
    return categoria.map(ROTULO_DA_CATEGORIA)


def preparar_tabela(tabela: pd.DataFrame, categorias: Categorias = "dashboard") -> pd.DataFrame:
    """Devolve a tabela pronta para ClassificadorAcademico.run_por_curso (variável `copia` do notebook)."""
    # Copia a tabela original
    copia = tabela.copy()

    # ── Célula 3 ──────────────────────────────────────────────────────────
    copia["CD_PERD_LETV"] = copia["CD_PERD_LETV"].apply(as_float)

    # Converte as colunas
    copia["adm_num"] = copia["PERIODO_ADMIS"].apply(para_semestre)
    copia["let_num"] = copia["CD_PERD_LETV"].apply(para_semestre)

    # Para cada estudante, pega a admissão mínima e o período letivo máximo
    resumo = copia.groupby("codigo_estudante").agg(
        adm_min=("adm_num", "min"),
        let_max=("let_num", "max"),
    )

    # Calcula quantidade de períodos
    resumo["qtd_periodos"] = resumo["let_max"] - resumo["adm_min"] + 1

    copia = copia.merge(
        resumo["qtd_periodos"],
        on="codigo_estudante",
        how="right",
    )
    copia = copia.drop(columns=["adm_num", "let_num"])

    # ── Célula 4 — situação acadêmica ─────────────────────────────────────
    if categorias == "dashboard":
        copia["DS_TP_SIT_ACAD"] = _situacao_dashboard(copia)
    else:
        copia["DS_TP_SIT_ACAD"] = copia["DS_TP_SIT_ACAD"].map(_MAPA_NOTEBOOK)
        copia["DS_TP_SIT_ACAD"] = copia["DS_TP_SIT_ACAD"].mask(
            (copia["qtd_periodos"] > 12) & (copia["DS_TP_SIT_ACAD"] != "CONCLUSÃO"), "ALUNOS RETIDOS"
        )

    # ── Célula 6 — médias finais nulas ────────────────────────────────────
    # Tratar uma das medias finas nulas: alunos reprovados no período especial
    mascara = copia["CD_PERD_LETV"] == 2020.3
    copia = copia[~(mascara & copia["NU_MEDIA_FIM"].isna())]

    # Tratar uma das medias finas nulas: reprovado por falta
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_SIT_HIST"] == "REPROVADO") & (copia["NU_MEDIA_FIM"].isna()) & ~(copia["NM_COMPNT_CURR"].isna()), -5
    )

    # Tratar uma das medias finais nulas: dispensado ou cancelado
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_SIT_HIST"] == "DISPENSADO") & (copia["NU_MEDIA_FIM"].isna()), -3
    )

    # Tratar uma das medias finais nulas: cancelado
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_SIT_HIST"] == "CANCELADO") & (copia["NU_MEDIA_FIM"].isna()), -3
    )

    # Tratar uma das medias finais nulas: evasão
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_TP_SIT_ACAD"] == "EVASÃO") & (copia["NU_MEDIA_FIM"].isna()), -6
    )

    # Tratar uma das medias finais nulas: alunos retidos
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_TP_SIT_ACAD"] == "ALUNOS RETIDOS") & (copia["NU_MEDIA_FIM"].isna()), -4
    )

    # Tratar uma das medias finais nulas: NM_COMPNT_CURR não nulos
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        ~(copia["NM_COMPNT_CURR"].isna()) & (copia["NU_MEDIA_FIM"].isna()), -3
    )

    # Tratar uma das medias finais nulas: alunos ativos
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_TP_SIT_ACAD"] == "ALUNOS ATIVOS") & (copia["NU_MEDIA_FIM"].isna()), -2
    )

    # Tratar uma das medias finais nulas: alunos cocluidos
    copia["NU_MEDIA_FIM"] = copia["NU_MEDIA_FIM"].mask(
        (copia["DS_TP_SIT_ACAD"] == "CONCLUSÃO") & (copia["NU_MEDIA_FIM"].isna()), -2
    )

    # ── Célula 7 — total de faltas nulas ──────────────────────────────────
    # Tratar uma das faltas nulas: evasão
    copia["NU_TOT_FALTAS"] = copia["NU_TOT_FALTAS"].mask(
        (copia["DS_TP_SIT_ACAD"] == "EVASÃO") & (copia["NU_TOT_FALTAS"].isna()), -4
    )

    # Tratar uma das faltas nulas: dispensado ou cancelado
    copia["NU_TOT_FALTAS"] = copia["NU_TOT_FALTAS"].mask(
        (copia["DS_TP_SIT_ACAD"] == "ALUNOS RETIDOS") & (copia["NU_TOT_FALTAS"].isna()), -3
    )

    # Tratar uma das faltas nulas: cancelado
    copia["NU_TOT_FALTAS"] = copia["NU_TOT_FALTAS"].mask(
        (copia["DS_TP_SIT_ACAD"] == "ALUNOS ATIVOS") & (copia["NU_TOT_FALTAS"].isna()), -2
    )

    # Tratar uma das faltas nulas: conclusão
    copia["NU_TOT_FALTAS"] = copia["NU_TOT_FALTAS"].mask(
        (copia["DS_TP_SIT_ACAD"] == "CONCLUSÃO") & (copia["NU_TOT_FALTAS"].isna()), -1
    )

    # ── Célula 8 — disciplina nula ────────────────────────────────────────
    copia["NM_COMPNT_CURR"] = copia["NM_COMPNT_CURR"].mask(copia["NM_COMPNT_CURR"].isna(), "Ausência de disciplina")
    copia["DS_SIT_HIST"] = copia["DS_SIT_HIST"].mask(copia["DS_SIT_HIST"].isna(), "Não aplicável")

    return copia
