"""Erros de domínio do fluxo pergunta → SQL → resposta."""


class ChatError(Exception):
    """Base. A mensagem é exibida ao usuário, então deve ser em português e sem detalhes internos."""

    status_code = 500


class LLMNotConfiguredError(ChatError):
    status_code = 503


class LLMProviderError(ChatError):
    status_code = 502


class UnsafeSQLError(ChatError):
    """SQL gerado não passou na validação (escrita, várias instruções, tabela desconhecida...)."""

    status_code = 422


class SQLExecutionError(ChatError):
    status_code = 422


class DatabaseUnavailableError(ChatError):
    status_code = 503
