"""Etapa 1 do chat: pergunta em linguagem natural → SQL (SQLite)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.core.errors import LLMProviderError
from app.services.llm import LLMClient, LLMMessage

# Pares pergunta → SQL que ensinam o modelo a usar as colunas *_busca e as
# regras de negócio. Todos são executados em tests/test_database.py.
EXEMPLOS: list[tuple[str, str]] = [
    (
        "Qual foi a média da turma em Cálculo Diferencial e Integral 1 no período 2019.2?",
        "SELECT ROUND(AVG(media_final), 2) AS media_turma FROM matriculas"
        " WHERE disciplina_busca LIKE '%CALCULO DIFERENCIAL E INTEGRAL 1%' AND periodo_letivo = '2019.2'",
    ),
    (
        "Quais cursos possuem maior taxa de evasão?",
        "SELECT curso, COUNT(*) AS total_alunos, SUM(evadiu) AS evadidos,"
        " ROUND(100.0 * SUM(evadiu) / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos GROUP BY curso ORDER BY taxa_evasao_pct DESC",
    ),
    (
        "Qual curso teve maior taxa de evasão no período 2024.1?",
        "SELECT curso, COUNT(*) AS total_alunos, SUM(categoria = 'EVADIDO') AS evadidos,"
        " ROUND(100.0 * SUM(categoria = 'EVADIDO') / COUNT(*), 1) AS taxa_evasao_pct"
        " FROM alunos_periodo WHERE periodo_letivo = '2024.1'"
        " GROUP BY curso ORDER BY taxa_evasao_pct DESC",
    ),
    (
        "Qual a taxa de retenção de Engenharia Civil em 2023.2?",
        "SELECT COUNT(*) AS total_alunos, SUM(categoria = 'RETIDO') AS retidos,"
        " ROUND(100.0 * SUM(categoria = 'RETIDO') / COUNT(*), 1) AS taxa_retencao_pct"
        " FROM alunos_periodo WHERE curso_busca LIKE '%ENGENHARIA CIVIL%' AND periodo_letivo = '2023.2'",
    ),
    (
        "Quais disciplinas possuem maior taxa de reprovação?",
        "SELECT disciplina, SUM(aprovado) + SUM(reprovado) AS avaliados,"
        " ROUND(100.0 * SUM(reprovado) / (SUM(aprovado) + SUM(reprovado)), 1) AS taxa_reprovacao_pct"
        " FROM matriculas GROUP BY disciplina HAVING avaliados >= 30"
        " ORDER BY taxa_reprovacao_pct DESC LIMIT 10",
    ),
    (
        "Mostre a evolução dos concluintes.",
        "SELECT periodo_letivo, SUM(categoria = 'FORMADO') AS formados FROM alunos_periodo"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
    ),
    (
        "Gráfico de evadidos de Engenharia Civil de 2020.1 a 2023.2",
        "SELECT periodo_letivo, SUM(categoria = 'EVADIDO') AS evadidos FROM alunos_periodo"
        " WHERE curso_busca LIKE '%ENGENHARIA CIVIL%' AND periodo_letivo BETWEEN '2020.1' AND '2023.2'"
        " GROUP BY periodo_letivo ORDER BY periodo_letivo",
    ),
    (
        "Quantos alunos ativos tinha Engenharia Civil em 2022.2?",
        "SELECT COUNT(*) AS alunos_ativos FROM alunos_periodo"
        " WHERE curso_busca LIKE '%ENGENHARIA CIVIL%' AND periodo_letivo = '2022.2' AND categoria = 'ATIVO'",
    ),
    (
        "Quantos alunos estão retidos hoje em cada curso?",
        "SELECT curso, COUNT(*) AS retidos FROM alunos WHERE situacao_atual = 'RETIDO'"
        " GROUP BY curso ORDER BY retidos DESC",
    ),
]

SYSTEM_PROMPT = """\
Você é um especialista em SQL (SQLite) do Sigadash, painel acadêmico da Escola Politécnica.
Converta a pergunta do usuário em UMA consulta SQL de leitura sobre o banco abaixo.

{banco}

Regras para o SQL:
- Use somente as tabelas e colunas descritas. Apenas SELECT (CTEs são permitidas).
- Para filtrar curso ou disciplina por nome, use as colunas *_busca com LIKE e o termo em
  MAIÚSCULAS e SEM acentos (ex.: disciplina_busca LIKE '%CALCULO%'). Mostre ao usuário as colunas
  curso/disciplina originais.
- Dê nomes claros às colunas calculadas (AS media_turma, AS taxa_evasao_pct...).
- Arredonde médias e taxas com ROUND(..., 2) ou ROUND(..., 1); taxas em porcentagem.
- Para rankings ou listas longas, ordene e use LIMIT (padrão 10, a não ser que o usuário peça outro número).
- Em perguntas de "qual teve o maior/menor...", devolva o ranking ordenado (não LIMIT 1), para a resposta
  mostrar a comparação e revelar empates.
- Em taxas, traga também o numerador e o total (ex.: evadidos e total_alunos), para conferência.
- Nunca selecione codigo_estudante isolado sem agregação, a menos que o usuário peça alunos específicos.

Exemplos:
{exemplos}

Responda APENAS com um JSON no formato:
{{"relevante": true, "sql": "<consulta>"}}
Se a pergunta não puder ser respondida com esses dados (assunto fora do escopo, pedido para
alterar o banco, conversa casual...), responda:
{{"relevante": false, "sql": null, "motivo": "<explicação curta em português para o usuário>"}}
"""


@dataclass
class GeneratedSQL:
    relevante: bool
    sql: str | None
    motivo: str | None = None


def _formatar_exemplos() -> str:
    return "\n\n".join(f"Pergunta: {p}\nSQL: {s}" for p, s in EXEMPLOS)


def build_system_prompt(descricao_banco: str) -> str:
    return SYSTEM_PROMPT.format(banco=descricao_banco, exemplos=_formatar_exemplos())


def _parse(texto: str) -> GeneratedSQL:
    try:
        data = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("O modelo devolveu uma resposta em formato inesperado.") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("O modelo devolveu uma resposta em formato inesperado.")
    sql = data.get("sql")
    return GeneratedSQL(
        relevante=bool(data.get("relevante")) and bool(sql),
        sql=sql if isinstance(sql, str) else None,
        motivo=data.get("motivo") if isinstance(data.get("motivo"), str) else None,
    )


def generate_sql(
    llm: LLMClient,
    descricao_banco: str,
    pergunta: str,
    historico: list[LLMMessage],
    erro_anterior: tuple[str, str] | None = None,
) -> GeneratedSQL:
    """Gera o SQL. `erro_anterior` = (sql, mensagem) da tentativa que falhou, para o modelo corrigir."""
    messages: list[LLMMessage] = [*historico, {"role": "user", "content": pergunta}]
    if erro_anterior:
        sql_falho, erro = erro_anterior
        messages += [
            {"role": "assistant", "content": json.dumps({"relevante": True, "sql": sql_falho}, ensure_ascii=False)},
            {"role": "user", "content": f"Essa consulta falhou com o erro: {erro}\nCorrija e devolva o JSON."},
        ]
    return _parse(llm.complete(build_system_prompt(descricao_banco), messages, json_mode=True))
