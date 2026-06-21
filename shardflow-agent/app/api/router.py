from fastapi import APIRouter

from app.api.v1.context_switch import router as context_switch_router
from app.api.v1.conversation import router as conversation_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.memory import router as memory_router
from app.api.v1.session_routes import router as session_routes_router
from app.api.v1.sessions import router as sessions_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(conversation_router, tags=["conversation"])
api_router.include_router(knowledge_router, tags=["knowledge-base"])
api_router.include_router(sessions_router, tags=["sessions"])
api_router.include_router(session_routes_router, tags=["sessions"])
api_router.include_router(context_switch_router, tags=["context"])
api_router.include_router(memory_router, tags=["memory"])
