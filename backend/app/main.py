"""API do Sigadash.v2: Assistente IA (chat) e projeção do próximo semestre.

Rodar (a partir de backend/):  uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.errors import ChatError
from app.projecao.servico import ServicoProjecao

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # A projeção roda em segundo plano: a API já responde enquanto o modelo treina.
        if settings.projecao_ativa:
            app.state.projecao.iniciar()
        yield

    app = FastAPI(title="Sigadash.v2 — Assistente IA e Projeção", version="1.1.0", lifespan=lifespan)
    app.state.projecao = ServicoProjecao(
        csv_path=settings.projecao_csv_path,
        cache_path=settings.projecao_cache_path,
        periodos_ignorados=settings.projecao_periodos_ignorados_lista,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(ChatError)
    async def _chat_error(_: Request, exc: ChatError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    app.include_router(router)
    return app


app = create_app()
