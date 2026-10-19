"""Acesso somente leitura ao banco do chat.

Mesmo com o SQL já validado em services/sql_guard.py, a execução tem duas
travas próprias: a conexão abre o arquivo em modo `ro` e um authorizer do
SQLite nega qualquer operação que não seja leitura. Um timeout interrompe
consultas longas.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errors import DatabaseUnavailableError, SQLExecutionError

_ACOES_PERMITIDAS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_RECURSIVE,
}


def _authorizer(action: int, *_: Any) -> int:
    return sqlite3.SQLITE_OK if action in _ACOES_PERMITIDAS else sqlite3.SQLITE_DENY


@dataclass
class QueryResult:
    colunas: list[str]
    linhas: list[list[Any]]
    truncado: bool


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise DatabaseUnavailableError(
            "Banco de dados do assistente não encontrado. Gere-o com: python backend/scripts/build_database.py"
        )
    con = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
    return con


def execute_select(path: Path, sql: str, max_linhas: int, timeout_s: float) -> QueryResult:
    con = connect_readonly(path)
    deadline = time.monotonic() + timeout_s
    try:
        con.set_authorizer(_authorizer)
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        try:
            cur = con.execute(sql)
            linhas = cur.fetchmany(max_linhas + 1)
        except sqlite3.Error as exc:
            if "interrupted" in str(exc):
                raise SQLExecutionError("A consulta demorou demais e foi interrompida.") from exc
            raise SQLExecutionError(f"Erro ao executar a consulta: {exc}") from exc
        colunas = [d[0] for d in cur.description or []]
    finally:
        con.close()

    truncado = len(linhas) > max_linhas
    return QueryResult(colunas=colunas, linhas=[list(r) for r in linhas[:max_linhas]], truncado=truncado)
