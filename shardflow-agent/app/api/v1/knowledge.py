"""Internal knowledge base API for document processing and retrieval.

Endpoints:
    POST /internal/kb/process  — Java callback to trigger document processing
    POST /internal/kb/search    — Direct KB search (for testing/diagnostics)
    GET  /internal/kb/stats/{collection_name} — Collection statistics
    DELETE /internal/kb/collections/{name} — Drop a collection
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.layers.retrieval.kb_pipeline import (
    process_document, get_collection_stats, drop_collection,
)
from app.layers.retrieval.knowledge_searcher import knowledge_searcher, invalidate_index_cache
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/kb", tags=["knowledge-base"])


# ── Request/Response models ──

class ProcessRequest(BaseModel):
    document_id: str = Field(..., description="MySQL kb_document.id")
    file_path: str = Field(..., description="Absolute path to uploaded file")
    file_type: str = Field(..., description="File extension without dot (pdf, docx, md, ...)")
    collection_name: str = Field(..., description="Milvus collection name (kb_chunks_{user_id})")
    user_id: str = Field(..., description="User ID")
    callback_url: str | None = Field(None, description="URL to callback with processing result")


class ProcessResponse(BaseModel):
    success: bool
    document_id: str
    chunk_count: int
    elapsed_ms: float
    error: str | None = None


class SearchRequest(BaseModel):
    query: str
    collection_name: str
    top_k: int = 5
    threshold: float = 0.65


# ── Endpoints ──

@router.post("/process", response_model=ProcessResponse)
async def kb_process(req: ProcessRequest):
    """Process an uploaded document: parse → chunk → embed → store in Milvus."""
    logger.info("Processing document %s (%s) → collection %s", req.document_id, req.file_type, req.collection_name)

    result = await process_document(
        file_path=req.file_path,
        file_type=req.file_type,
        collection_name=req.collection_name,
        document_id=req.document_id,
        user_id=req.user_id,
    )

    invalidate_index_cache(req.collection_name)

    if req.callback_url and result["success"]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.put(
                    req.callback_url,
                    json={
                        "status": "READY",
                        "chunk_count": result["chunk_count"],
                    },
                    headers={"X-Internal-Token": settings.java_api_key},
                )
        except Exception as e:
            logger.warning("Callback to Java failed for doc %s: %s", req.document_id, e)

    return ProcessResponse(
        success=result["success"],
        document_id=req.document_id,
        chunk_count=result["chunk_count"],
        elapsed_ms=result["elapsed_ms"],
        error=result.get("error"),
    )


@router.post("/search")
async def kb_search(req: SearchRequest):
    """Direct knowledge base search (for testing/diagnostics)."""
    results = await knowledge_searcher.search(
        query=req.query,
        collection_name=req.collection_name,
        top_k=req.top_k,
        threshold=req.threshold,
    )
    return {
        "query": req.query,
        "collection": req.collection_name,
        "count": len(results),
        "results": [r.model_dump() for r in results],
    }


@router.get("/stats/{collection_name}")
async def kb_stats(collection_name: str):
    """Get collection statistics."""
    stats = get_collection_stats(collection_name)
    return stats


@router.delete("/collections/{collection_name}")
async def kb_drop_collection(collection_name: str):
    """Drop a Milvus collection (admin only)."""
    success = drop_collection(collection_name)
    invalidate_index_cache(collection_name)
    return {"success": success, "collection": collection_name}
