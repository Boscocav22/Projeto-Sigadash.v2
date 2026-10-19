from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SettingsDep, get_chat_service
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse, tags=["sistema"])
def health(settings: SettingsDep) -> HealthResponse:
    banco = settings.database_path.exists()
    llm = bool(settings.openai_api_key)
    return HealthResponse(status="ok" if banco and llm else "degradado", banco=banco, llm_configurado=llm)


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
def chat(req: ChatRequest, service: Annotated[ChatService, Depends(get_chat_service)]) -> ChatResponse:
    """Recebe uma pergunta, gera e executa o SQL e devolve a resposta em linguagem natural."""
    return service.responder(req)
