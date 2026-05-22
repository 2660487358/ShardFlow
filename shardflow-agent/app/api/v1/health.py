from fastapi import APIRouter
import httpx

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    java_status = "unreachable"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.java_base_url}/health")
            if resp.status_code == 200:
                java_status = "healthy"
    except Exception:
        pass

    return {
        "status": "ok",
        "java_api": java_status,
    }
