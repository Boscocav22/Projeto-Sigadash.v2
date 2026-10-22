from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.projecao.servico import ServicoProjecao
from app.services.chat_service import ChatService
from app.services.llm import LLMClient, build_llm_client

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm_client(settings: SettingsDep) -> LLMClient:
    return build_llm_client(settings)


def get_chat_service(settings: SettingsDep, llm: Annotated[LLMClient, Depends(get_llm_client)]) -> ChatService:
    return ChatService(llm, settings)


def get_servico_projecao(request: Request) -> ServicoProjecao:
    return request.app.state.projecao
