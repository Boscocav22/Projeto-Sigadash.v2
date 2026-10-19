"""Cliente de LLM.

O restante do backend depende só do protocolo `LLMClient`, então trocar de
provedor (ou usar um falso nos testes) não mexe no fluxo do chat.
"""

from __future__ import annotations

from typing import Protocol, TypedDict

from app.core.config import Settings
from app.core.errors import LLMNotConfiguredError, LLMProviderError


class LLMMessage(TypedDict):
    role: str  # "user" | "assistant"
    content: str


class LLMClient(Protocol):
    def complete(self, system: str, messages: list[LLMMessage], json_mode: bool = False) -> str: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str, timeout_s: float, base_url: str | None = None) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout_s)
        self._model = model

    def complete(self, system: str, messages: list[LLMMessage], json_mode: bool = False) -> str:
        import openai

        extra = {"response_format": {"type": "json_object"}} if json_mode else {}
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": system}, *messages],
                temperature=0,
                **extra,
            )
        except openai.OpenAIError as exc:
            raise LLMProviderError("Falha ao consultar o modelo de linguagem. Tente novamente.") from exc
        return resp.choices[0].message.content or ""


def build_llm_client(settings: Settings) -> LLMClient:
    if not settings.openai_api_key:
        raise LLMNotConfiguredError("Assistente indisponível: OPENAI_API_KEY não configurada no backend.")
    return OpenAIClient(settings.openai_api_key, settings.llm_model, settings.llm_timeout_s, settings.openai_base_url)
