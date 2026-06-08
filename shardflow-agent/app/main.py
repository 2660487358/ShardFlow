from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.infrastructure.callback_client import callback_client
    from app.infrastructure.redis_client import redis_client
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.model_client_manager import model_client_manager
    from app.layers.tool.http_executor import http_executor

    await redis_client.connect()

    # Phase 2 优化：启动时预热模型客户端连接池
    # 消除首次请求的 TCP+TLS 冷握手延迟（~200-500ms）
    try:
        await model_client_manager.warm_up()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Model client warm-up skipped: %s", e)

    yield
    await model_client_manager.close()
    await llm_router.close()
    await http_executor.close()
    await callback_client.close()
    await redis_client.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ShardFlow Python Inference Layer",
        description="Core reasoning engine for ShardFlow - ReAct loop orchestration via LangGraph",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/agent/v1")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    from app.config import settings
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=True)
