package com.shardflow.kb.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import com.shardflow.kb.service.KbService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/kb")
@RequiredArgsConstructor
public class KbController {

    private final KbService kbService;

    // ── Collections ──

    @GetMapping("/collections")
    public Result<Map<String, Object>> listCollections() {
        List<KbCollectionEntity> collections = kbService.listCollections(UserContext.getUserId());
        return Result.ok(Map.of("collections", collections, "total", collections.size()));
    }

    @PostMapping("/collections")
    public Result<KbCollectionEntity> createCollection(@RequestBody KbCollectionEntity collection) {
        collection.setUserId(UserContext.getUserId());
        return Result.ok(kbService.createCollection(collection));
    }

    @GetMapping("/collections/{id}")
    public Result<?> getCollection(@PathVariable String id) {
        return kbService.getCollection(id)
            .map(Result::ok)
            .orElse(Result.fail(404, "Collection not found"));
    }

    @PutMapping("/collections/{id}")
    public Result<?> updateCollection(@PathVariable String id, @RequestBody KbCollectionEntity updates) {
        return kbService.updateCollection(id, updates)
            .map(Result::ok)
            .orElse(Result.fail(404, "Collection not found"));
    }

    @DeleteMapping("/collections/{id}")
    public Result<?> deleteCollection(@PathVariable String id) {
        boolean deleted = kbService.deleteCollection(id);
        return deleted ? Result.ok(Map.of("deleted", true)) : Result.fail(404, "Collection not found");
    }

    // ── Documents ──

    @GetMapping("/collections/{collectionId}/documents")
    public Result<Map<String, Object>> listDocuments(@PathVariable String collectionId) {
        List<KbDocumentEntity> docs = kbService.listDocuments(collectionId);
        return Result.ok(Map.of("documents", docs, "total", docs.size()));
    }

    @PostMapping("/collections/{collectionId}/documents")
    public Result<KbDocumentEntity> uploadDocument(@PathVariable String collectionId,
                                                    @RequestBody KbDocumentEntity doc) {
        doc.setCollectionId(collectionId);
        doc.setUserId(UserContext.getUserId());
        return Result.ok(kbService.addDocument(doc));
    }

    @DeleteMapping("/documents/{id}")
    public Result<?> deleteDocument(@PathVariable String id) {
        boolean deleted = kbService.deleteDocument(id);
        return deleted ? Result.ok(Map.of("deleted", true)) : Result.fail(404, "Document not found");
    }
}
