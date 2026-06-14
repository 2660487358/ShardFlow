package com.shardflow.kb.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import com.shardflow.kb.service.KbService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.kb.repository.KbCollectionRepository;
import com.shardflow.kb.repository.KbDocumentRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/v1/kb/callback")
@RequiredArgsConstructor
public class KbCallbackController {

    private final KbDocumentRepository documentRepo;
    private final KbCollectionRepository collectionRepo;

    @PutMapping("/document")
    public Result<?> onDocumentProcessed(@RequestBody Map<String, Object> payload) {
        String documentId = (String) payload.get("document_id");
        String status = (String) payload.get("status");
        int chunkCount = payload.containsKey("chunk_count") ? ((Number) payload.get("chunk_count")).intValue() : 0;
        String error = (String) payload.get("error");

        log.info("KB callback: doc={}, status={}, chunks={}, error={}", documentId, status, chunkCount, error);

        KbDocumentEntity doc = documentRepo.selectOne(
            new LambdaQueryWrapper<KbDocumentEntity>().eq(KbDocumentEntity::getDocumentCode, documentId));
        if (doc == null) {
            log.warn("Callback for unknown document: {}", documentId);
            return Result.fail(404, "Document not found");
        }

        doc.setStatus("ERROR".equals(status) ? "ERROR" : "READY");
        if (error != null && !error.isBlank()) {
            doc.setErrorMsg(error);
        }
        documentRepo.updateById(doc);

        if ("READY".equals(status) && chunkCount > 0) {
            KbCollectionEntity coll = collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, doc.getCollectionId()));
            if (coll != null) {
                coll.setChunkCount((coll.getChunkCount() != null ? coll.getChunkCount() : 0) + chunkCount);
                collectionRepo.updateById(coll);
            }
        }

        return Result.ok(Map.of("acknowledged", true));
    }
}
