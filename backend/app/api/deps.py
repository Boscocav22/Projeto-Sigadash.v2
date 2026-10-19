from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.services.chat_service import ChatService
from app.services.llm import LLMClient, build_llm_client

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm_client(settings: SettingsDep) -> LLMClient:
    return build_llm_client(settings)


def get_chat_service(settings: SettingsDep, llm: Annotated[LLMClient, Depends(get_llm_client)]) -> ChatService:
    return ChatService(llm, settings)
