from fastapi import FastAPI

from app.api.router import api_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="KnowledgeBridge Python Inference Layer",
        description="Core reasoning engine for KnowledgeBridge - ReAct loop orchestration via LangGraph",
        version="0.1.0",
    )
    app.include_router(api_router, prefix="/agent/v1")
    return app


app = create_app()
