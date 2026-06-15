package com.shardflow.kb.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import com.shardflow.kb.mq.DeleteCommandMessage;
import com.shardflow.kb.mq.KbMessageProducer;
import com.shardflow.kb.service.GrpcKnowledgeClient;
import com.shardflow.kb.service.KbService;
import com.shardflow.kb.service.MinioStorageService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.time.Instant;
import java.util.*;

@Slf4j
@RestController
@RequestMapping("/api/v1/kb")
@RequiredArgsConstructor
public class KbController {

    private final KbService kbService;
    private final MinioStorageService minioStorageService;
    private final GrpcKnowledgeClient grpcKnowledgeClient;
    private final KbMessageProducer messageProducer;

    private static final long MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB

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
        Optional<KbCollectionEntity> result = kbService.updateCollection(id, updates);
        if (result.isEmpty()) return Result.fail(404, "Collection not found");
        return Result.ok(result.get());
    }

    @PutMapping("/collections/{id}/archive")
    public Result<?> archiveCollection(@PathVariable String id) {
        Optional<KbCollectionEntity> existing = kbService.getCollection(id);
        if (existing.isEmpty()) return Result.fail(404, "Collection not found");

        KbCollectionEntity col = existing.get();
        if (!"ACTIVE".equals(col.getStatus())) {
            return Result.fail(400, "Only ACTIVE collections can be archived, current status: " + col.getStatus());
        }

        Optional<KbCollectionEntity> result = kbService.archiveCollection(id);
        if (result.isEmpty()) return Result.fail(500, "Archive failed");

        log.info("Knowledge base {} archived by user {}", id, UserContext.getUserId());
        return Result.ok(result.get());
    }

    @PutMapping("/collections/{id}/unarchive")
    public Result<?> unarchiveCollection(@PathVariable String id) {
        Optional<KbCollectionEntity> existing = kbService.getCollection(id);
        if (existing.isEmpty()) return Result.fail(404, "Collection not found");

        KbCollectionEntity col = existing.get();
        if (!"ARCHIVED".equals(col.getStatus())) {
            return Result.fail(400, "Only ARCHIVED collections can be unarchived, current status: " + col.getStatus());
        }

        Optional<KbCollectionEntity> result = kbService.unarchiveCollection(id);
        if (result.isEmpty()) return Result.fail(500, "Unarchive failed");

        log.info("Knowledge base {} unarchived by user {}", id, UserContext.getUserId());
        return Result.ok(result.get());
    }

    @DeleteMapping("/collections/{id}")
    public Result<?> deleteCollection(@PathVariable String id) {
        Optional<KbCollectionEntity> existing = kbService.getCollection(id);
        if (existing.isEmpty()) return Result.fail(404, "Collection not found");

        KbCollectionEntity coll = existing.get();

        // Soft-delete in PostgreSQL (mark DELETING)
        coll.setStatus("DELETING");
        kbService.updateCollection(coll.getCollectionCode(), coll);

        // Send MQ delete command to Python
        List<KbDocumentEntity> docs = kbService.listDocuments(coll.getCollectionCode());
        List<String> docIdList = docs.stream().map(KbDocumentEntity::getDocumentCode).toList();

        messageProducer.sendDeleteCommand(DeleteCommandMessage.builder()
            .kbId(coll.getCollectionCode())
            .type("DELETE_KB")
            .userId(coll.getUserId())
            .docIdList(docIdList)
            .initiatedAt(Instant.now().toString())
            .build());

        return Result.ok(Map.of("deleted", true, "status", "DELETING"));
    }

    // ── Documents ──

    @GetMapping("/collections/{collectionId}/documents")
    public Result<Map<String, Object>> listDocuments(@PathVariable String collectionId) {
        List<KbDocumentEntity> docs = kbService.listDocuments(collectionId);
        return Result.ok(Map.of("documents", docs, "total", docs.size()));
    }

    @PostMapping("/collections/{collectionId}/documents")
    public Result<?> uploadDocument(@PathVariable String collectionId,
                                    @RequestParam("file") MultipartFile file) {
        String userId = UserContext.getUserId();

        // Block upload if collection is archived
        Optional<KbCollectionEntity> collOpt = kbService.getCollection(collectionId);
        if (collOpt.isEmpty()) return Result.fail(404, "Collection not found");
        if ("ARCHIVED".equals(collOpt.get().getStatus())) {
            return Result.fail(400, "Cannot upload to an archived collection. Please unarchive it first.");
        }

        if (file.isEmpty()) {
            return Result.fail(400, "File is empty");
        }
        if (file.getSize() > MAX_FILE_SIZE) {
            return Result.fail(413, "File size exceeds 20MB limit");
        }

        String originalFilename = file.getOriginalFilename();
        String fileType = extractExtension(originalFilename);

        if (!isSupported(fileType)) {
            return Result.fail(400, "Unsupported file type: " + fileType);
        }

        // Create document record
        KbDocumentEntity doc = new KbDocumentEntity();
        doc.setCollectionId(collectionId);
        doc.setUserId(userId);
        doc.setFilename(originalFilename);
        doc.setFileType(fileType);
        doc.setFileSize(file.getSize());
        doc.setParseStrategy(determineStrategy(fileType));
        doc.setStatus("PENDING");

        KbDocumentEntity saved = kbService.addDocument(doc);

        // Upload to MinIO
        try {
            String minioUrl = minioStorageService.upload(userId, collectionId, saved.getDocumentCode(), file);
            saved.setMinioUrl(minioUrl);
            kbService.updateDocument(saved);
        } catch (Exception e) {
            log.error("MinIO upload failed for doc {}: {}", saved.getDocumentCode(), e.getMessage());
            saved.setStatus("ERROR");
            saved.setErrorMsg("Storage upload failed: " + e.getMessage());
            kbService.updateDocument(saved);
            return Result.ok(saved);
        }

        // Dispatch to Python via gRPC
        try {
            String taskId = "task-" + saved.getDocumentCode();
            String uploadTime = Instant.now().toString();
            grpcKnowledgeClient.submitUploadTask(
                taskId, collectionId, saved.getMinioUrl(),
                originalFilename, fileType, file.getSize(),
                userId, uploadTime
            );
            log.info("gRPC task dispatched: task={}, doc={}", taskId, saved.getDocumentCode());
        } catch (Exception e) {
            log.warn("gRPC dispatch failed for doc {}: {}. Doc will remain PENDING for retry.",
                    saved.getDocumentCode(), e.getMessage());
        }

        return Result.ok(saved);
    }

    @DeleteMapping("/documents/{id}")
    public Result<?> deleteDocument(@PathVariable String id) {
        Optional<KbDocumentEntity> existingOpt = kbService.getDocument(id);
        if (existingOpt.isEmpty()) return Result.fail(404, "Document not found");

        KbDocumentEntity doc = existingOpt.get();

        // Send MQ delete command for single doc
        messageProducer.sendDeleteCommand(DeleteCommandMessage.builder()
            .kbId(doc.getCollectionId())
            .type("DELETE_DOC")
            .userId(doc.getUserId())
            .docId(id)
            .initiatedAt(Instant.now().toString())
            .build());

        // Soft-delete
        doc.setStatus("DELETING");
        kbService.updateDocument(doc);

        return Result.ok(Map.of("deleted", true, "status", "DELETING"));
    }

    // ── Helpers ──

    private static final Set<String> SUPPORTED_EXTENSIONS = Set.of(
        "pdf", "docx", "md", "txt", "py", "java", "ts", "tsx", "js",
        "go", "rs", "yaml", "yml", "json", "xml"
    );

    private boolean isSupported(String extension) {
        return SUPPORTED_EXTENSIONS.contains(extension.toLowerCase());
    }

    private String determineStrategy(String fileType) {
        return switch (fileType.toLowerCase()) {
            case "pdf" -> "layout";
            case "docx" -> "layout";
            case "md" -> "heading";
            case "txt" -> "paragraph";
            case "py", "java", "ts", "tsx", "js", "go", "rs" -> "ast";
            case "yaml", "yml", "json", "xml" -> "style";
            default -> "paragraph";
        };
    }

    private String extractExtension(String filename) {
        if (filename == null || !filename.contains(".")) return "bin";
        return filename.substring(filename.lastIndexOf('.') + 1).toLowerCase();
    }
}
