"""Orquestra o fluxo do chat: pergunta → SQL → consulta → resposta em linguagem natural."""

from __future__ import annotations

import logging

from app.core.config import Settings
from app.core.errors import SQLExecutionError, UnsafeSQLError
from app.db.catalog import TABELAS_PERMITIDAS, descricao_banco
from app.db.database import QueryResult, execute_select
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.answer_writer import resultado_vazio, write_answer
from app.services.chart_spec import escolher_grafico
from app.services.llm import LLMClient, LLMMessage
from app.services.sql_generator import generate_sql
from app.services.sql_guard import validate_select

log = logging.getLogger(__name__)

FORA_DO_ESCOPO = (
    "Só consigo responder perguntas sobre os dados acadêmicos do Sigadash "
    "(alunos, cursos, disciplinas, notas, evasão e formação)."
)


class ChatService:
    def __init__(self, llm: LLMClient, settings: Settings) -> None:
        self._llm = llm
        self._settings = settings

    def _historico(self, req: ChatRequest) -> list[LLMMessage]:
        ultimos = req.historico[-self._settings.max_historico :] if self._settings.max_historico else []
        return [{"role": h.role, "content": h.text} for h in ultimos]

    def _consultar(self, req: ChatRequest) -> tuple[str, QueryResult] | str:
        """Gera e executa o SQL, reenviando o erro ao modelo para correção. Devolve texto se fora do escopo."""
        banco = descricao_banco(self._settings.database_path)
        historico = self._historico(req)
        erro_anterior: tuple[str, str] | None = None

        for tentativa in range(1, self._settings.max_tentativas_sql + 1):
            gerado = generate_sql(self._llm, banco, req.pergunta, historico, erro_anterior)
            if not gerado.relevante or not gerado.sql:
                return gerado.motivo or FORA_DO_ESCOPO
            try:
                sql = validate_select(gerado.sql, TABELAS_PERMITIDAS)
                resultado = execute_select(
                    self._settings.database_path,
                    sql,
                    self._settings.max_linhas_resposta,
                    self._settings.sql_timeout_s,
                )
                return sql, resultado
            except (UnsafeSQLError, SQLExecutionError) as exc:
                log.warning("tentativa %d falhou: %s | sql=%s", tentativa, exc, gerado.sql)
                if tentativa == self._settings.max_tentativas_sql:
                    raise
                erro_anterior = (gerado.sql, str(exc))

        raise AssertionError("inalcançável")

    def responder(self, req: ChatRequest) -> ChatResponse:
        consulta = self._consultar(req)
        if isinstance(consulta, str):
            return ChatResponse(resposta=consulta)

        sql, resultado = consulta
        redigida = write_answer(self._llm, req.pergunta, sql, resultado, self._settings.max_linhas_contexto)
        grafico = None
        if not resultado_vazio(resultado):
            # o modelo sugere; se a sugestão faltar ou não for desenhável, vale a regra fixa
            grafico, origem = escolher_grafico(redigida.grafico_sugerido, resultado.colunas, resultado.linhas)
            log.info("gráfico: %s (%s)", grafico.tipo if grafico else "nenhum", origem)
        return ChatResponse(
            resposta=redigida.texto,
            sql=sql,
            colunas=resultado.colunas,
            dados=resultado.linhas,
            total_linhas=len(resultado.linhas),
            truncado=resultado.truncado,
            grafico=grafico,
        )
