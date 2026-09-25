"""
common.py — camada de leitura e utilitários compartilhados.

  1. load_csv: única função do projeto que toca o CSV, devolve um
     DataFrame limpo.
  2. Utilitários de período: parse_period, semestres_cursados, sort_periods,
     period_key e normalize_text.

"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable, Optional, Tuple

import pandas as pd

CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig" 

COL_ESTUDANTE = "codigo_estudante"
COL_CURSO = "NM_PROGR_FORM"
COL_ADMISSAO = "PERIODO_ADMIS"
COL_ANO_CONC = "NU_ANO_CONC"
COL_SIT_ACAD = "DS_TP_SIT_ACAD"
COL_DISCIPLINA = "NM_COMPNT_CURR"
COL_SIT_HIST = "DS_SIT_HIST"
COL_PERIODO = "CD_PERD_LETV"
COL_MEDIA = "NU_MEDIA_FIM"
COL_FALTAS = "NU_TOT_FALTAS"

NUMERIC_COLS = (COL_MEDIA, COL_FALTAS)

_PERIOD_RE = re.compile(r"^\s*(\d{4})\.(\d)\s*$")
_WS_RE = re.compile(r"\s+")


# Leitura do CSV
def load_csv(path: str | Path) -> pd.DataFrame:
    """Lê e limpa o CSV. Célula vazia vira NA."""
    df = pd.read_csv(
        path,
        sep=CSV_SEP,
        encoding=CSV_ENCODING,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
    )
    df.columns = [c.strip() for c in df.columns]

    for col in df.columns:
        s = df[col].astype("string").str.strip()
        df[col] = s.mask(s == "", pd.NA)

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    df = df[df[COL_ESTUDANTE].notna()].reset_index(drop=True)
    return df


# Normalização do texto (trim + colapsa espaços + maiúsculas + sem acentos) 
def normalize_text(value: object) -> Optional[str]:
    """Os valores exibidos no dashboard continuam sendo os textos originais do CSV.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    s = _WS_RE.sub(" ", str(value).strip()).upper()
    if not s:
        return None
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


# Períodos
def parse_period(value: object) -> Optional[Tuple[int, int]]:
    """"AAAA.S" -> (ano, semestre)."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    m = _PERIOD_RE.match(str(value))
    if not m:
        return None
    ano, sem = int(m.group(1)), int(m.group(2))
    if sem < 1:
        return None
    return ano, sem


def period_key(value: object) -> Tuple[int, int]:
    """Chave de ordenação cronológica. Período inválido vai para o fim."""
    p = parse_period(value)
    return p if p is not None else (10**9, 10**9)


def sort_periods(periods: Iterable[object]) -> list[str]:
    """Remove duplicados/inválidos e ordena cronologicamente."""
    validos = {str(p).strip() for p in periods if parse_period(p) is not None}
    return sorted(validos, key=period_key)


def semestres_cursados(periodo_inicial: object, periodo_final: object) -> Optional[int]:
    """2×(ano_final−ano_inicial) + (semestre_final−semestre_inicial) + 1.

    Devolve o valor BRUTO (pode ser <= 0 quando a admissão foi registrada depois
    do primeiro histórico).
    """
    ini = parse_period(periodo_inicial)
    fim = parse_period(periodo_final)
    if ini is None or fim is None:
        return None
    return 2 * (fim[0] - ini[0]) + (fim[1] - ini[1]) + 1
