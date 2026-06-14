"""RAG Knowledge Base App — gRPC task handler + MinIO + MQ integration."""
import asyncio
import json
import logging
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.config import settings
from app.layers.retrieval.kb_pipeline import process_document
from app.layers.retrieval.knowledge_searcher import invalidate_index_cache
from app.knowledge.grpc_server import create_grpc_server

logger = logging.getLogger(__name__)

_grpc_server = None
_minio_client: Minio | None = None
_mq_connection = None
_mq_channel = None
_mq_consumer_tag: str | None = None

EXCHANGE = "kb.events"
RK_UPLOAD_COMPLETE = "upload.complete"
RK_DELETE_COMPLETE = "delete.complete"
QUEUE_DELETE_COMMAND = "kb.delete.command"


def get_minio_client() -> Minio:
    global _minio_client
    if _minio_client is None:
        _minio_client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=False,
        )
    return _minio_client


def _download_from_minio(minio_url: str) -> Path:
    """Download a file from MinIO to a temp location. Returns the temp path.

    minio_url can be either:
      - Full path: bucket/object_key (e.g. shardflow-kb/kb/user123/coll/doc.pdf)
      - Object key only: kb/user123/coll/doc.pdf (bucket inferred from settings)
    """
    client = get_minio_client()
    parts = minio_url.split("/", 1)
    if len(parts) == 2 and parts[0] == settings.minio_bucket:
        # Already has bucket prefix
        bucket, object_path = parts[0], parts[1]
    elif len(parts) == 2:
        # First segment might be a bucket or part of the object path
        # Try to detect: if first segment is a known bucket, use it; otherwise prepend default bucket
        try:
            client.stat_object(parts[0], parts[1])
            bucket, object_path = parts[0], parts[1]
        except S3Error:
            bucket = settings.minio_bucket
            object_path = minio_url
    else:
        bucket = settings.minio_bucket
        object_path = minio_url

    suffix = Path(object_path).suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()

    try:
        client.fget_object(bucket, object_path, str(tmp_path))
        logger.info("Downloaded from MinIO: %s/%s -> %s", bucket, object_path, tmp_path)
    except S3Error as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"MinIO download failed: {e}") from e

    return tmp_path


async def _publish_message(routing_key: str, payload: dict):
    """Publish a message to RabbitMQ."""
    global _mq_channel
    if _mq_channel is None or _mq_channel.is_closed:
        logger.error("MQ channel not available, dropping message: %s", routing_key)
        return
    import aio_pika
    message = aio_pika.Message(
        body=json.dumps(payload).encode(),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await _mq_channel.default_exchange.publish(message, routing_key=routing_key)
    logger.info("MQ published: %s", routing_key)


def _handle_upload_task(request) -> None:
    task_id = request.task_id
    minio_url = request.minio_url
    metadata = request.metadata
    doc_id = task_id.replace("task-", "")
    kb_id = request.kb_id  # Actual kb_collection ID for metadata tagging

    async def _process():
        tmp_path = None
        try:
            # Download from MinIO.
            # Java stores objectPath (e.g. kb/user123/coll/doc.pdf) as minio_url.
            # _download_from_minio handles both full and object-key-only formats.
            tmp_path = _download_from_minio(minio_url)
            collection_name = f"kb_chunks_{metadata.uploader}"

            # Progress callback: publish intermediate status via MQ
            async def _progress_cb(status: str, extra: dict | None = None):
                """Publish PARSING/EMBEDDING intermediate status to Java via MQ."""
                try:
                    payload = {
                        "taskId": task_id,
                        "type": "UPLOAD_PROGRESS",
                        "status": status,
                        "kbId": kb_id,
                        "docId": doc_id,
                        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }
                    if extra:
                        payload["extra"] = extra
                    await _publish_message("upload.progress", payload)
                except Exception as e:
                    logger.warning("Failed to publish progress for %s: %s", task_id, e)

            result = await process_document(
                file_path=str(tmp_path),
                file_type=metadata.file_type,
                collection_name=collection_name,
                document_id=doc_id,
                user_id=metadata.uploader,
                kb_id=kb_id,
                progress_callback=_progress_cb,
            )

            invalidate_index_cache(collection_name)

            success = result["success"]
            await _publish_message(RK_UPLOAD_COMPLETE, {
                "taskId": task_id,
                "type": "UPLOAD_COMPLETE",
                "status": "SUCCESS" if success else "FAILED",
                "kbId": request.kb_id,
                "result": {
                    "docId": doc_id,
                    "chunkCount": result.get("chunk_count", 0),
                    "embeddingModel": settings.kb_embedding_model,
                    "processTimeMs": int(result.get("elapsed_ms", 0)),
                    "tokenCount": 0,
                } if success else None,
                "error": None if success else {
                    "code": "PROCESS_ERROR",
                    "message": result.get("error", "Unknown error"),
                    "retryable": False,
                },
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })

        except Exception as e:
            logger.exception("Upload task %s failed", task_id)
            await _publish_message(RK_UPLOAD_COMPLETE, {
                "taskId": task_id,
                "type": "UPLOAD_COMPLETE",
                "status": "FAILED",
                "kbId": request.kb_id,
                "result": None,
                "error": {"code": "PROCESS_ERROR", "message": str(e), "retryable": False},
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    threading.Thread(target=lambda: asyncio.run(_process()), daemon=True).start()


async def _handle_delete_message(message: dict):
    """Handle DELETE_KB / DELETE_DOC messages from Java via MQ."""
    kb_id = message.get("kbId", "")
    msg_type = message.get("type", "")
    doc_id_list = message.get("docIdList", [])
    doc_id = message.get("docId")
    user_id = message.get("userId", "")

    # Resolve collection name: kb_chunks_{userId}
    # If userId is provided, use it; otherwise fall back to kb_id (backward compat)
    collection_name = f"kb_chunks_{user_id}" if user_id else kb_id

    logger.info("MQ recv delete: type=%s, kb=%s, userId=%s, collection=%s, docs=%s",
                msg_type, kb_id, user_id, collection_name, doc_id_list or doc_id)

    try:
        from pymilvus import Collection, utility
        from app.layers.retrieval.kb_pipeline import connect_milvus
        from app.layers.retrieval.knowledge_searcher import invalidate_index_cache
        connect_milvus()

        deleted_count = 0
        failed_docs = []

        if not utility.has_collection(collection_name):
            logger.warning("Collection %s not found for delete, treating as already clean", collection_name)
            # Still publish success — collection doesn't exist means nothing to delete
            await _publish_message(RK_DELETE_COMPLETE, {
                "kbId": kb_id,
                "userId": user_id,
                "type": "DELETE_COMPLETE",
                "status": "SUCCESS",
                "deletedCount": 0,
                "failedDocs": [],
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
            return

        # Single doc delete: query and delete chunks by doc_id
        if msg_type == "DELETE_DOC" and doc_id:
            try:
                col = Collection(collection_name)
                col.load()
                expr = f'document_id == "{doc_id}"'
                entities = col.query(expr=expr, output_fields=["id", "document_id"])
                if entities:
                    pks = [e["id"] for e in entities]
                    col.delete(f'id in {pks}')
                    col.flush()
                    deleted_count = len(pks)
                    logger.info("Deleted %d chunks for doc %s in collection %s",
                                deleted_count, doc_id, collection_name)
            except Exception as e:
                logger.error("Delete doc %s failed: %s", doc_id, e)
                failed_docs.append(doc_id)

        # Full KB delete: wipe all chunks for this kb_id
        elif msg_type == "DELETE_KB":
            try:
                col = Collection(collection_name)
                col.load()
                expr = f'collection_id == "{kb_id}"'
                entities = col.query(expr=expr, output_fields=["id"])
                if entities:
                    pks = [e["id"] for e in entities]
                    col.delete(f'id in {pks}')
                    col.flush()
                    deleted_count = len(pks)
                    logger.info("Deleted %d chunks for kb %s in collection %s",
                                deleted_count, kb_id, collection_name)
            except Exception as e:
                logger.error("Delete kb %s from collection %s failed: %s",
                            kb_id, collection_name, e)

        invalidate_index_cache(collection_name)

        await _publish_message(RK_DELETE_COMPLETE, {
            "kbId": kb_id,
            "userId": user_id,
            "type": "DELETE_COMPLETE",
            "status": "SUCCESS" if not failed_docs else "FAILED",
            "deletedCount": deleted_count,
            "failedDocs": failed_docs,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    except Exception as e:
        logger.exception("Delete handler failed for kb=%s", kb_id)
        await _publish_message(RK_DELETE_COMPLETE, {
            "kbId": kb_id,
            "userId": user_id,
            "type": "DELETE_COMPLETE",
            "status": "FAILED",
            "deletedCount": 0,
            "failedDocs": doc_id_list or ([doc_id] if doc_id else []),
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })


async def _mq_consumer_loop():
    """Consume delete command messages from RabbitMQ."""
    import aio_pika
    global _mq_connection, _mq_channel, _mq_consumer_tag

    retry_count = 0
    while True:
        try:
            url = f"amqp://{settings.rabbitmq_user}:{settings.rabbitmq_password}@{settings.rabbitmq_host}:{settings.rabbitmq_port}/{settings.rabbitmq_vhost}"
            _mq_connection = await aio_pika.connect_robust(url)
            _mq_channel = await _mq_connection.channel()
            await _mq_channel.set_qos(prefetch_count=1)

            # Declare exchange
            exchange = await _mq_channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)

            # Declare DLX
            dlx = await _mq_channel.declare_exchange("kb.dlx", aio_pika.ExchangeType.TOPIC, durable=True)
            dlq = await _mq_channel.declare_queue("kb.dlq", durable=True)
            await dlq.bind(dlx, routing_key="kb.dlq")

            # Declare delete command queue
            queue = await _mq_channel.declare_queue(
                QUEUE_DELETE_COMMAND, durable=True,
                arguments={"x-dead-letter-exchange": "kb.dlx", "x-dead-letter-routing-key": "kb.dlq"}
            )
            await queue.bind(exchange, routing_key="delete.command")

            async def on_message(message: aio_pika.IncomingMessage):
                """Process delete command with retry logic: NACK on failure, up to 3 retries then dead-letter."""
                retry_count = 0
                # Read x-death header for retry tracking
                if message.headers and "x-death" in message.headers:
                    x_death = message.headers["x-death"]
                    if isinstance(x_death, list) and len(x_death) > 0:
                        death_info = x_death[0] if isinstance(x_death[0], dict) else {}
                        retry_count = death_info.get("count", 0)

                try:
                    body = json.loads(message.body.decode())
                    await _handle_delete_message(body)
                    # Success: ACK the message
                    await message.ack()
                except Exception as e:
                    logger.exception("Failed to process delete message (retry=%d): %s", retry_count, e)
                    if retry_count >= 3:
                        # Max retries exceeded: reject to dead-letter queue
                        logger.error("Message exceeded 3 retries, sending to DLQ: %s", message.body[:200])
                        await message.reject(requeue=False)
                    else:
                        # Retry: NACK with requeue so it gets redelivered
                        await message.nack(requeue=True)

            _mq_consumer_tag = await queue.consume(on_message)
            logger.info("MQ consumer started on queue: %s", QUEUE_DELETE_COMMAND)
            retry_count = 0
            break

        except Exception as e:
            retry_count += 1
            if retry_count > 3:
                logger.error("MQ consumer failed after 3 retries")
                break
            delay = min(5 * retry_count, 30)
            logger.warning("MQ connect attempt %d failed: %s. Retrying in %ds...", retry_count, e, delay)
            await asyncio.sleep(delay)


async def start_mq_consumer():
    """Start MQ consumer in background."""
    asyncio.create_task(_mq_consumer_loop())


async def stop_mq_consumer():
    global _mq_connection
    if _mq_connection:
        await _mq_connection.close()
        logger.info("MQ connection closed")


def start_grpc_server(port: int = 50051) -> threading.Thread:
    global _grpc_server
    server = create_grpc_server(_handle_upload_task, port)
    _grpc_server = server
    server.start()
    logger.info("gRPC KnowledgeService started on port %d", port)

    def _wait():
        server.wait_for_termination()

    t = threading.Thread(target=_wait, daemon=True)
    t.start()
    return t


def stop_grpc_server():
    global _grpc_server
    if _grpc_server:
        _grpc_server.stop(grace=5)
        logger.info("gRPC KnowledgeService stopped")
