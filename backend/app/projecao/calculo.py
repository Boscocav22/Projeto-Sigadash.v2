"""Executa a projeção a partir de df_tabela_final.csv, como a célula 10 do notebook."""

from __future__ import annotations

import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.projecao.classificador import ClassificadorAcademico
from app.projecao.preparo import Categorias, preparar_tabela

COLUNA_CURSO = "NM_PROGR_FORM"
COLUNAS_OBRIGATORIAS = {
    "codigo_estudante", COLUNA_CURSO, "PERIODO_ADMIS", "DS_TP_SIT_ACAD",
    "NM_COMPNT_CURR", "DS_SIT_HIST", "CD_PERD_LETV", "NU_MEDIA_FIM", "NU_TOT_FALTAS",
}

# Parâmetros da chamada run_por_curso da célula 10.
PARAMETROS_RF = {
    "min_absoluto": None,
    "n_estimators": 500,
    "max_depth": 12,
    "min_samples_leaf": 10,
    "incluir_ingresso": True,
}


class ProjecaoErro(Exception):
    """Falha esperada (CSV ausente/ilegível, nenhuma projeção). A mensagem vai para o usuário."""


def ler_csv(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise ProjecaoErro(f"Arquivo de dados não encontrado: {csv_path.name}")
    try:
        # Mesma leitura do notebook (célula 2).
        tabela = pd.read_csv(csv_path, sep=";")
    except Exception as exc:  # noqa: BLE001 — qualquer falha de leitura vira mensagem para o usuário
        raise ProjecaoErro(f"Não foi possível ler {csv_path.name}: {exc}") from exc
    faltando = COLUNAS_OBRIGATORIAS - set(tabela.columns)
    if faltando:
        raise ProjecaoErro(f"{csv_path.name} não tem as colunas: {', '.join(sorted(faltando))}")
    if tabela.empty:
        raise ProjecaoErro(f"{csv_path.name} está vazio.")
    return tabela


def periodo_seguinte_ao_ultimo(tabela: pd.DataFrame) -> str:
    """Período-alvo: o semestre seguinte ao último período letivo do CSV (ex.: 2025.2 → 2026.1)."""
    chaves = [ClassificadorAcademico._chave_periodo(p) for p in tabela["CD_PERD_LETV"].dropna().unique()]
    validas = [c for c in chaves if len(c) == 3 and c[0] == 0]
    if not validas:
        raise ProjecaoErro("Nenhum período letivo válido no CSV.")
    _, ano, sem = max(validas)
    return f"{ano + 1}.1" if sem >= 2 else f"{ano}.{sem + 1}"


def calcular_projecao(
    csv_path: Path,
    periodos_ignorados: list[str],
    categorias: Categorias = "dashboard",
) -> dict:
    """Lê o CSV, prepara, treina um Random Forest por curso e devolve o resumo projetado."""
    inicio = time.perf_counter()
    tabela = ler_csv(csv_path)
    periodo_alvo = periodo_seguinte_ao_ultimo(tabela)
    copia = preparar_tabela(tabela, categorias=categorias)

    with warnings.catch_warnings():
        # Avisos de depreciação do pandas 3 em select_dtypes (presentes também no notebook).
        warnings.simplefilter("ignore", category=Warning)
        resultado = ClassificadorAcademico().run_por_curso(
            tabela=copia,
            coluna_curso=COLUNA_CURSO,
            periodo_alvo=periodo_alvo,
            # Os períodos vêm como float (2025.1) do CSV, como no notebook.
            periodos_suspeitos_manuais=[float(p) for p in periodos_ignorados] or None,
            exportar_csv=False,
            **PARAMETROS_RF,
        )

    resumo = resultado["resumo_geral"]
    linhas = [
        {
            "curso": str(r[COLUNA_CURSO]),
            "periodo_base": ClassificadorAcademico._rotulo_periodo(r["periodo_base"]),
            "periodo_alvo": ClassificadorAcademico._rotulo_periodo(r["periodo_alvo"]),
            "situacao": str(r["situacao"]),
            "quantidade": int(r["quantidade_projetada"]),
            "proporcao": float(r["proporcao_projetada"]),
        }
        for _, r in resumo.iterrows()
    ]
    erros = [
        {"curso": str(r[COLUNA_CURSO]), "erro": str(r["erro"])}
        for _, r in resultado["erros"].iterrows()
    ]
    if not linhas:
        detalhe = f" ({erros[0]['curso']}: {erros[0]['erro']})" if erros else ""
        raise ProjecaoErro(f"O algoritmo não gerou projeção para nenhum curso{detalhe}.")

    return {
        "periodo_alvo": periodo_alvo,
        "periodos_ignorados": list(periodos_ignorados),
        "linhas": linhas,
        "erros": erros,
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duracao_s": round(time.perf_counter() - inicio, 1),
    }
