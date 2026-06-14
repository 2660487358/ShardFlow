"""gRPC Knowledge Service Server."""
import asyncio
import logging
from concurrent import futures

import grpc

from app.config import settings
from app.generated.knowledge_pb2 import TaskAck
from app.generated.knowledge_pb2_grpc import KnowledgeServiceServicer, add_KnowledgeServiceServicer_to_server

logger = logging.getLogger(__name__)


class KnowledgeServiceServicerImpl(KnowledgeServiceServicer):
    def __init__(self, task_handler):
        self._task_handler = task_handler

    def SubmitUploadTask(self, request, context):
        task_id = request.task_id
        logger.info("gRPC SubmitUploadTask received: task=%s kb=%s file=%s",
                    task_id, request.kb_id, request.metadata.filename)

        if not request.minio_url:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("minio_url is required")
            return TaskAck(task_id=task_id, accepted=False, message="minio_url is required")

        try:
            self._task_handler(request)
            return TaskAck(task_id=task_id, accepted=True, message="task accepted")
        except Exception as e:
            logger.exception("Task handler error for %s", task_id)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return TaskAck(task_id=task_id, accepted=False, message=str(e))


def create_grpc_server(task_handler, port: int = 50051) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    servicer = KnowledgeServiceServicerImpl(task_handler)
    add_KnowledgeServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server
