"""Validação do SQL gerado pelo LLM antes de executá-lo.

Aceita apenas uma única consulta de leitura (SELECT, com ou sem CTE/UNION)
sobre as tabelas conhecidas. Substitui a antiga lista de palavras proibidas,
que bloqueava consultas legítimas (ex.: coluna "updated") e deixava passar
outras (ex.: PRAGMA, ATTACH).
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.core.errors import UnsafeSQLError

_FENCE_RE = re.compile(r"^\s*```(?:sql)?\s*|\s*```\s*$", re.IGNORECASE)

_NOS_PROIBIDOS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.Command,
    exp.Pragma,
    exp.Attach,
    exp.Detach,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)


def strip_markdown(sql: str) -> str:
    return _FENCE_RE.sub("", sql).strip()


def validate_select(sql: str, tabelas_permitidas: frozenset[str]) -> str:
    """Devolve o SQL limpo se for seguro; senão levanta UnsafeSQLError."""
    sql = strip_markdown(sql).rstrip(";").strip()
    if not sql:
        raise UnsafeSQLError("Nenhuma consulta SQL foi gerada.")

    try:
        statements = [s for s in sqlglot.parse(sql, read="sqlite") if s is not None]
    except ParseError as exc:
        raise UnsafeSQLError(f"SQL inválido: {exc}") from exc

    if len(statements) != 1:
        raise UnsafeSQLError("Apenas uma consulta por pergunta é permitida.")

    (root,) = statements
    if not isinstance(root, exp.Query):
        raise UnsafeSQLError("Apenas consultas de leitura (SELECT) são permitidas.")

    for node in root.walk():
        if isinstance(node, _NOS_PROIBIDOS):
            raise UnsafeSQLError("A consulta contém comandos que não são de leitura.")

    ctes = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        nome = table.name.lower()
        if not nome:  # funções de tabela, ex.: json_each(...)
            raise UnsafeSQLError("Funções de tabela não são permitidas.")
        if table.db or table.catalog:
            raise UnsafeSQLError("Apenas o banco principal pode ser consultado.")
        if nome not in ctes and nome not in tabelas_permitidas:
            raise UnsafeSQLError(f"Tabela desconhecida: {table.name}")

    return sql
