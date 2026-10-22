from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import SettingsDep, get_chat_service, get_servico_projecao
from app.projecao.servico import ServicoProjecao
from app.schemas.chat import ChatRequest, ChatResponse, HealthResponse
from app.schemas.projecao import ProjecaoResponse
from app.services.chat_service import ChatService

ProjecaoDep = Annotated[ServicoProjecao, Depends(get_servico_projecao)]

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


@router.get("/projecao", response_model=ProjecaoResponse, tags=["projeção"])
def projecao(servico: ProjecaoDep) -> dict:
    """Projeção do próximo semestre por curso e situação (status "processando" enquanto calcula)."""
    return servico.estado()


@router.post("/projecao/atualizar", response_model=ProjecaoResponse, status_code=202, tags=["projeção"])
def atualizar_projecao(servico: ProjecaoDep, settings: SettingsDep) -> dict:
    """Recalcula a projeção a partir do CSV, ignorando o cache. Não faz nada se já houver um cálculo em andamento."""
    if settings.projecao_ativa:
        servico.iniciar(forcar=True)
    return servico.estado()
