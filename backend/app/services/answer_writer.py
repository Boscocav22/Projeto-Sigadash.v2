"""Etapa 3 do chat: resultado da consulta → resposta em linguagem natural."""

from __future__ import annotations

from typing import Any

from app.db.database import QueryResult
from app.services.llm import LLMClient

SYSTEM_PROMPT = """\
Você é o Assistente IA do Sigadash, painel acadêmico da Escola Politécnica.
Recebe a pergunta do usuário, a consulta SQL executada e o resultado dela.
Responda à pergunta em português, de forma clara e direta (no máximo um parágrafo curto ou uma
lista curta), usando SOMENTE os números do resultado — nunca invente valores.
- Formate números no padrão brasileiro (vírgula decimal) e indique % quando forem taxas.
- Se o resultado tiver muitas linhas, destaque os principais itens e diga que a tabela completa
  está logo abaixo da resposta.
- Não mostre o SQL nem fale de tabelas ou colunas do banco.
"""

SEM_RESULTADOS = (
    "Não encontrei registros para essa pergunta. Confira o nome do curso, da disciplina ou o "
    "período letivo (formato AAAA.S, ex.: 2023.1)."
)


def _fmt(v: Any) -> str:
    return "NULL" if v is None else str(v)


def _tabela(resultado: QueryResult, max_linhas: int) -> str:
    linhas = resultado.linhas[:max_linhas]
    corpo = "\n".join(" | ".join(_fmt(v) for v in linha) for linha in linhas)
    total = len(resultado.linhas)
    rodape = ""
    if total > max_linhas or resultado.truncado:
        rodape = f"\n(mostrando {len(linhas)} de {'mais de ' if resultado.truncado else ''}{total} linhas)"
    return f"{' | '.join(resultado.colunas)}\n{corpo}{rodape}"


def _resultado_vazio(resultado: QueryResult) -> bool:
    return not resultado.linhas or all(v is None for linha in resultado.linhas for v in linha)


def write_answer(llm: LLMClient, pergunta: str, sql: str, resultado: QueryResult, max_linhas: int) -> str:
    if _resultado_vazio(resultado):
        return SEM_RESULTADOS
    conteudo = (
        f"Pergunta: {pergunta}\n\n"
        f"SQL executado:\n{sql}\n\n"
        f"Resultado:\n{_tabela(resultado, max_linhas)}"
    )
    return llm.complete(SYSTEM_PROMPT, [{"role": "user", "content": conteudo}]).strip()
