package com.shardflow.kb.mq;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import com.shardflow.kb.config.RabbitMqConfig;
import com.shardflow.kb.repository.KbCollectionRepository;
import com.shardflow.kb.repository.KbDocumentRepository;
import com.shardflow.kb.service.KbProgressService;
import com.shardflow.kb.service.MilvusQueryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.util.Map;

@Slf4j
@Component
@RequiredArgsConstructor
public class KbMessageConsumer {

    private final KbDocumentRepository documentRepo;
    private final KbCollectionRepository collectionRepo;
    private final MilvusQueryService milvusQueryService;
    private final KbProgressService progressService;

    @RabbitListener(queues = RabbitMqConfig.QUEUE_UPLOAD_CALLBACK)
    public void onUploadComplete(UploadCallbackMessage msg) {
        log.info("MQ recv UPLOAD_COMPLETE: task={}, status={}", msg.getTaskId(), msg.getStatus());

        if (!"UPLOAD_COMPLETE".equals(msg.getType())) return;

        String docId = msg.getTaskId();
        if (docId != null && docId.startsWith("task-")) {
            docId = docId.substring(5); // strip "task-" prefix
        }

        KbDocumentEntity doc = documentRepo.selectOne(
            new LambdaQueryWrapper<KbDocumentEntity>().eq(KbDocumentEntity::getDocumentCode, docId));
        if (doc == null) {
            log.warn("UPLOAD_COMPLETE for unknown doc: {}", docId);
            return;
        }

        if ("SUCCESS".equals(msg.getStatus())) {
            doc.setStatus("READY");
            doc.setErrorMsg(null);

            if (msg.getResult() != null && msg.getResult().getChunkCount() > 0) {
                KbCollectionEntity coll = collectionRepo.selectOne(
                    new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, doc.getCollectionId()));
                if (coll != null) {
                    coll.setChunkCount((coll.getChunkCount() != null ? coll.getChunkCount() : 0) + msg.getResult().getChunkCount());
                    collectionRepo.updateById(coll);
                }
            }
        } else {
            doc.setStatus("ERROR");
            if (msg.getError() != null) {
                doc.setErrorMsg(msg.getError().getMessage());
            }
        }

        documentRepo.updateById(doc);

        // Push real-time progress via WebSocket
        progressService.pushFromUploadCallback(msg, docId, doc.getUserId());
    }

    @RabbitListener(queues = RabbitMqConfig.QUEUE_UPLOAD_PROGRESS)
    public void onUploadProgress(Map<String, Object> msg) {
        String status = (String) msg.getOrDefault("status", "");
        String docId = (String) msg.getOrDefault("docId", "");
        String kbId = (String) msg.getOrDefault("kbId", "");
        String taskId = (String) msg.getOrDefault("taskId", "");

        log.debug("MQ recv UPLOAD_PROGRESS: task={}, status={}", taskId, status);

        // Map intermediate statuses to document state
        if ("PARSING".equals(status) || "EMBEDDING".equals(status) || "CHUNKING".equals(status)) {
            // Update document status to intermediate state
            String docCode = taskId.startsWith("task-") ? taskId.substring(5) : taskId;
            KbDocumentEntity doc = documentRepo.selectOne(
                new LambdaQueryWrapper<KbDocumentEntity>().eq(KbDocumentEntity::getDocumentCode, docCode));
            if (doc != null && !"ERROR".equals(doc.getStatus()) && !"READY".equals(doc.getStatus())) {
                doc.setStatus(status);
                documentRepo.updateById(doc);

                // Push progress via WebSocket
                String userId = doc.getUserId();
                int progressPct = "PARSING".equals(status) ? 30 : "EMBEDDING".equals(status) ? 70 : 50;
                progressService.pushProgress(userId, docCode, status, progressPct, null);
            }
        }
    }

    @RabbitListener(queues = RabbitMqConfig.QUEUE_DELETE_CALLBACK)
    public void onDeleteComplete(DeleteCallbackMessage msg) {
        log.info("MQ recv DELETE_COMPLETE: kb={}, status={}, deleted={}",
                msg.getKbId(), msg.getStatus(), msg.getDeletedCount());

        if (!"DELETE_COMPLETE".equals(msg.getType())) return;

        if ("SUCCESS".equals(msg.getStatus())) {
            // Verify via Milvus read-only before physical delete
            boolean milvusClean = milvusQueryService.verifyDeleted(msg.getUserId(), msg.getKbId());
            if (milvusClean) {
                int docDeleted = documentRepo.delete(
                    new LambdaQueryWrapper<KbDocumentEntity>()
                        .eq(KbDocumentEntity::getCollectionId, msg.getKbId())
                );
                int collDeleted = collectionRepo.delete(
                    new LambdaQueryWrapper<KbCollectionEntity>()
                        .eq(KbCollectionEntity::getCollectionCode, msg.getKbId())
                );
                log.info("MQ DELETE_COMPLETE cleanup: docs={}, colls={}", docDeleted, collDeleted);
            } else {
                log.error("MILVUS STILL HAS DATA for kb={}, keeping MySQL records as DELETING", msg.getKbId());
            }
        } else {
            log.error("DELETE_COMPLETE FAILED: kb={}, failedDocs={}",
                    msg.getKbId(), msg.getFailedDocs());
        }
    }
}
