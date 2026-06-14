from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.infrastructure.callback_client import callback_client
    from app.infrastructure.redis_client import redis_client
    from app.layers.agent_core.llm_router import llm_router
    from app.layers.agent_core.model_client_manager import model_client_manager
    from app.layers.agent_core.memory_degradation import memory_degradation
    from app.layers.agent_core.memory_lifecycle import memory_lifecycle
    from app.layers.tool.http_executor import http_executor
    from app.knowledge.app import start_grpc_server, stop_grpc_server, start_mq_consumer, stop_mq_consumer

    await redis_client.connect()

    # Phase 2 优化：启动时预热模型客户端连接池
    try:
        await model_client_manager.warm_up()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Model client warm-up skipped: %s", e)

    # Start background memory subsystems
    try:
        await memory_degradation.start()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Memory degradation retry loop skipped: %s", e)

    try:
        await memory_lifecycle.start_background_cleanup()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Memory lifecycle cleanup skipped: %s", e)

    # Start gRPC KnowledgeService server
    try:
        from app.config import settings
        start_grpc_server(port=settings.grpc_port)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("gRPC KnowledgeService startup skipped: %s", e)

    # Start MQ consumer for delete commands
    try:
        await start_mq_consumer()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("MQ consumer startup skipped: %s", e)

    yield

    await stop_mq_consumer()
    stop_grpc_server()
    await model_client_manager.close()
    await llm_router.close()
    await http_executor.close()
    await memory_degradation.stop()
    await memory_lifecycle.stop_background_cleanup()
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
