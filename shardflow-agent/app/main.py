from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.infrastructure.callback_client import callback_client
    from app.infrastructure.redis_client import redis_client
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.tool.http_executor import http_executor

    await redis_client.connect()
    yield
    await llm_router.close()
    await http_executor.close()
    await callback_client.close()
    await redis_client.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title="KnowledgeBridge Python Inference Layer",
        description="Core reasoning engine for KnowledgeBridge - ReAct loop orchestration via LangGraph",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/agent/v1")
    return app


app = create_app()
