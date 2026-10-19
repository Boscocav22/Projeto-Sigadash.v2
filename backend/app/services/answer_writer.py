"""Etapa 3 do chat: resultado da consulta → resposta em linguagem natural + sugestão de gráfico."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.db.database import QueryResult
from app.services.chart_spec import classificar_colunas
from app.services.llm import LLMClient

SYSTEM_PROMPT = """\
Você é o Assistente IA do Sigadash, painel acadêmico da Escola Politécnica.
Recebe a pergunta do usuário, a consulta SQL executada e o resultado dela.

1) Responda à pergunta em português, de forma clara e direta (no máximo um parágrafo curto ou uma
lista curta), usando SOMENTE os números do resultado — nunca invente valores.
- Formate números no padrão brasileiro (vírgula decimal) e indique % quando forem taxas.
- Se o resultado tiver muitas linhas, destaque os principais itens e diga que a tabela completa
  está logo abaixo da resposta.
- Não mostre o SQL nem fale de tabelas ou colunas do banco.

2) Sugira um gráfico que ajude a ler o resultado, ou null se ele não ajudar.
- tipo: "linha" (evolução no tempo; x precisa ser uma coluna temporal), "barra" (comparar poucas
  categorias de nome curto) ou "barra_horizontal" (rankings e categorias de nome longo).
- x: nome EXATO de uma coluna temporal ou categórica. y: lista com 1 a 3 nomes EXATOS de colunas
  numéricas, todas na mesma unidade (nunca misture contagem com porcentagem).
- Escolha em y a métrica que responde à pergunta. Use 2 ou 3 séries só para comparar medidas
  da mesma unidade (ex.: aprovados e reprovados).
- titulo: curto, em português.
- Use null quando o resultado for um único valor ou quando o usuário pedir explicitamente só texto.
  Se o usuário pedir um gráfico, sugira um sempre que os dados permitirem.

Responda APENAS com um JSON no formato:
{"resposta": "<texto>", "grafico": {"tipo": "...", "x": "...", "y": ["..."], "titulo": "..."} | null}
"""

SEM_RESULTADOS = (
    "Não encontrei registros para essa pergunta. Confira o nome do curso, da disciplina ou o "
    "período letivo (formato AAAA.S, ex.: 2023.1)."
)

_ROTULO_TIPO = {"temporal": "temporal", "numerica": "numérica", "categorica": "categórica"}


@dataclass
class RespostaRedigida:
    texto: str
    grafico_sugerido: Any = None  # dict ainda não validado (ver chart_spec.validar_grafico)


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


def _descrever_colunas(resultado: QueryResult) -> str:
    tipos = classificar_colunas(resultado.colunas, resultado.linhas)
    return ", ".join(f"{c} ({_ROTULO_TIPO[tipos[c]]})" for c in resultado.colunas)


def resultado_vazio(resultado: QueryResult) -> bool:
    return not resultado.linhas or all(v is None for linha in resultado.linhas for v in linha)


def _parse(texto: str) -> RespostaRedigida:
    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        # Sem JSON válido, aproveita o texto como resposta e segue sem sugestão de gráfico.
        return RespostaRedigida(texto=texto.strip())
    if not isinstance(data, dict) or not isinstance(data.get("resposta"), str):
        return RespostaRedigida(texto=texto.strip())
    return RespostaRedigida(texto=data["resposta"].strip(), grafico_sugerido=data.get("grafico"))


def write_answer(llm: LLMClient, pergunta: str, sql: str, resultado: QueryResult, max_linhas: int) -> RespostaRedigida:
    if resultado_vazio(resultado):
        return RespostaRedigida(texto=SEM_RESULTADOS)
    conteudo = (
        f"Pergunta: {pergunta}\n\n"
        f"SQL executado:\n{sql}\n\n"
        f"Colunas: {_descrever_colunas(resultado)}\n\n"
        f"Resultado:\n{_tabela(resultado, max_linhas)}"
    )
    return _parse(llm.complete(SYSTEM_PROMPT, [{"role": "user", "content": conteudo}], json_mode=True))
