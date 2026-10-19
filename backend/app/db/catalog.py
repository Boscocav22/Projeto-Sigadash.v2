"""Descrição do banco enviada ao LLM.

A parte fixa (tabelas, colunas e regras de negócio) é escrita à mão, porque é
ela que ensina o modelo a responder do mesmo jeito que o dashboard. A parte
variável (cursos, períodos, situações) é lida do próprio banco, para que o
modelo use exatamente os textos gravados.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.db.database import connect_readonly

TABELAS_PERMITIDAS = frozenset({"alunos", "alunos_periodo", "matriculas"})

SCHEMA_DESCRICAO = """\
TABLE alunos  -- uma linha por aluno
  codigo_estudante   TEXT PRIMARY KEY
  curso              TEXT     -- nome do curso como gravado (com acentos)
  curso_busca        TEXT     -- curso em MAIÚSCULAS e SEM acentos, para filtros com LIKE
  periodo_admissao   TEXT     -- 'AAAA.S'
  ano_conclusao      INTEGER  -- ano de conclusão informado (pode ser NULL)
  periodo_atual      TEXT     -- último período em que o aluno tem registro
  semestre_atual     INTEGER  -- semestre cursado no período atual
  situacao_atual     TEXT     -- 'ATIVO' | 'EVADIDO' | 'RETIDO' | 'FORMADO' (situação mais recente)
  evadiu             INTEGER  -- 1 se o aluno teve algum período EVADIDO
  periodo_evasao     TEXT     -- primeiro período EVADIDO
  semestre_evasao    INTEGER  -- semestre cursado na evasão
  tipo_evasao        TEXT     -- tipo de saída (ex.: 'EXCLUÍDO', 'DESVINCULADO')
  formou             INTEGER  -- 1 se o aluno se formou
  periodo_formacao   TEXT     -- período de referência da formação
  semestre_formacao  INTEGER  -- semestre cursado na formação

TABLE alunos_periodo  -- uma linha por (aluno, período letivo)
  codigo_estudante  TEXT  -- FK alunos.codigo_estudante
  curso             TEXT
  curso_busca       TEXT
  periodo_letivo    TEXT     -- 'AAAA.S'
  semestre          INTEGER  -- semestre cursado naquele período
  categoria         TEXT     -- 'ATIVO' | 'EVADIDO' | 'RETIDO' | 'FORMADO' naquele período

TABLE matriculas  -- uma linha por matrícula de um aluno em uma disciplina
  id                   INTEGER PRIMARY KEY
  codigo_estudante     TEXT  -- FK alunos.codigo_estudante
  curso                TEXT
  curso_busca          TEXT
  disciplina           TEXT  -- nome da disciplina como gravado (com acentos)
  disciplina_busca     TEXT  -- disciplina em MAIÚSCULAS e SEM acentos, para filtros com LIKE
  periodo_letivo       TEXT  -- 'AAAA.S'
  situacao_disciplina  TEXT  -- situação original no histórico (pode ser NULL)
  aprovado             INTEGER  -- 1 se APROVADO ou DISPENSADO
  reprovado            INTEGER  -- 1 se REPROVADO
  media_final          REAL     -- nota final de 0 a 10 (pode ser NULL)
  total_faltas         REAL     -- total de faltas (pode ser NULL)
"""

REGRAS_NEGOCIO = """\
- Todos os dados são da Escola Politécnica (único polo).
- Períodos letivos têm o formato 'AAAA.S' (ex.: '2023.1'); a comparação de texto respeita a ordem cronológica.
- Situação do aluno: FORMADO > EVADIDO > RETIDO > ATIVO. RETIDO = aluno ativo que já passou do 13º semestre.
- "Alunos ativos/evadidos/retidos/formados" sem período informado = alunos.situacao_atual.
  Com período informado, use alunos_periodo.categoria no período pedido.
- Taxa de evasão de um grupo = alunos com evadiu = 1 ÷ total de alunos do grupo.
  Taxa de formação = alunos com formou = 1 ÷ total de alunos do grupo.
- Taxa de aprovação de uma disciplina = SUM(aprovado) ÷ (SUM(aprovado) + SUM(reprovado));
  taxa de reprovação = SUM(reprovado) ÷ (SUM(aprovado) + SUM(reprovado)).
- Médias de nota e de faltas consideram só valores não nulos (AVG já ignora NULL).
- Concluintes/formados por período: alunos.periodo_formacao.
"""


@lru_cache(maxsize=4)
def _valores_do_banco(path: Path, mtime: float) -> str:  # mtime invalida o cache quando o banco é regerado
    con = connect_readonly(path)
    try:
        cursos = [r[0] for r in con.execute("SELECT DISTINCT curso FROM alunos ORDER BY curso")]
        (p_min, p_max) = con.execute(
            "SELECT MIN(periodo_letivo), MAX(periodo_letivo) FROM alunos_periodo"
        ).fetchone()
        situacoes = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT situacao_disciplina FROM matriculas"
                " WHERE situacao_disciplina IS NOT NULL ORDER BY 1"
            )
        ]
        tipos_evasao = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT tipo_evasao FROM alunos WHERE tipo_evasao IS NOT NULL ORDER BY 1"
            )
        ]
    finally:
        con.close()

    return (
        f"- Cursos (alunos.curso): {', '.join(repr(c) for c in cursos)}\n"
        f"- Períodos disponíveis: de '{p_min}' a '{p_max}'\n"
        f"- Valores de matriculas.situacao_disciplina: {', '.join(repr(s) for s in situacoes)}\n"
        f"- Valores de alunos.tipo_evasao: {', '.join(repr(t) for t in tipos_evasao)}\n"
    )


def descricao_banco(path: Path) -> str:
    valores = _valores_do_banco(path, path.stat().st_mtime) if path.exists() else ""
    return (
        f"<schema>\n{SCHEMA_DESCRICAO}</schema>\n\n"
        f"<regras>\n{REGRAS_NEGOCIO}</regras>\n\n"
        f"<valores>\n{valores}</valores>"
    )
