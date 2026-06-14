package com.shardflow.kb.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import com.shardflow.kb.repository.KbCollectionRepository;
import com.shardflow.kb.repository.KbDocumentRepository;
import com.shardflow.kb.service.KbService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class KbServiceImpl implements KbService {

    private final KbCollectionRepository collectionRepo;
    private final KbDocumentRepository documentRepo;

    // ── Collections ──

    @Override
    public List<KbCollectionEntity> listCollections(String userId) {
        return collectionRepo.selectList(
            new LambdaQueryWrapper<KbCollectionEntity>()
                .eq(KbCollectionEntity::getUserId, userId)
                .orderByDesc(KbCollectionEntity::getUpdatedAt)
        );
    }

    @Override
    public Optional<KbCollectionEntity> getCollection(String id) {
        // id can be either numeric PK or collection_code
        try {
            long numericId = Long.parseLong(id);
            return Optional.ofNullable(collectionRepo.selectById(numericId));
        } catch (NumberFormatException e) {
            return Optional.ofNullable(collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, id)));
        }
    }

    @Override
    public KbCollectionEntity createCollection(KbCollectionEntity c) {
        if (c.getCollectionCode() == null || c.getCollectionCode().isBlank()) {
            c.setCollectionCode("kb-" + UUID.randomUUID().toString().substring(0, 8));
        }
        c.setStatus(c.getStatus() != null ? c.getStatus() : "ACTIVE");
        c.setDocCount(0);
        c.setChunkCount(0);
        collectionRepo.insert(c);
        return c;
    }

    @Override
    public Optional<KbCollectionEntity> updateCollection(String id, KbCollectionEntity updates) {
        KbCollectionEntity existing;
        try {
            long numericId = Long.parseLong(id);
            existing = collectionRepo.selectById(numericId);
        } catch (NumberFormatException e) {
            existing = collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, id));
        }
        if (existing == null) return Optional.empty();
        updates.setId(existing.getId());
        collectionRepo.updateById(updates);
        return Optional.of(collectionRepo.selectById(existing.getId()));
    }

    @Override
    public boolean deleteCollection(String id) {
        KbCollectionEntity existing;
        try {
            long numericId = Long.parseLong(id);
            existing = collectionRepo.selectById(numericId);
        } catch (NumberFormatException e) {
            existing = collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, id));
        }
        if (existing == null) return false;
        // Delete associated documents first
        documentRepo.delete(new LambdaQueryWrapper<KbDocumentEntity>()
            .eq(KbDocumentEntity::getCollectionId, existing.getCollectionCode()));
        return collectionRepo.deleteById(existing.getId()) > 0;
    }

    // ── Documents ──

    @Override
    public List<KbDocumentEntity> listDocuments(String collectionId) {
        return documentRepo.selectList(
            new LambdaQueryWrapper<KbDocumentEntity>()
                .eq(KbDocumentEntity::getCollectionId, collectionId)
                .orderByDesc(KbDocumentEntity::getCreatedAt)
        );
    }

    @Override
    public KbDocumentEntity addDocument(KbDocumentEntity doc) {
        if (doc.getDocumentCode() == null || doc.getDocumentCode().isBlank()) {
            doc.setDocumentCode("doc-" + UUID.randomUUID().toString().substring(0, 8));
        }
        doc.setStatus(doc.getStatus() != null ? doc.getStatus() : "PENDING");
        documentRepo.insert(doc);

        // Update collection doc count
        KbCollectionEntity coll = collectionRepo.selectOne(
            new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, doc.getCollectionId()));
        if (coll != null) {
            coll.setDocCount((coll.getDocCount() != null ? coll.getDocCount() : 0) + 1);
            collectionRepo.updateById(coll);
        }

        return doc;
    }

    @Override
    public boolean deleteDocument(String id) {
        KbDocumentEntity doc;
        try {
            long numericId = Long.parseLong(id);
            doc = documentRepo.selectById(numericId);
        } catch (NumberFormatException e) {
            doc = documentRepo.selectOne(
                new LambdaQueryWrapper<KbDocumentEntity>().eq(KbDocumentEntity::getDocumentCode, id));
        }
        if (doc == null) return false;
        boolean deleted = documentRepo.deleteById(doc.getId()) > 0;
        if (deleted) {
            KbCollectionEntity coll = collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, doc.getCollectionId()));
            if (coll != null && coll.getDocCount() != null && coll.getDocCount() > 0) {
                coll.setDocCount(coll.getDocCount() - 1);
                collectionRepo.updateById(coll);
            }
        }
        return deleted;
    }

    @Override
    public void updateDocument(KbDocumentEntity doc) {
        documentRepo.updateById(doc);
    }

    @Override
    public Optional<KbDocumentEntity> getDocument(String id) {
        try {
            long numericId = Long.parseLong(id);
            return Optional.ofNullable(documentRepo.selectById(numericId));
        } catch (NumberFormatException e) {
            return Optional.ofNullable(documentRepo.selectOne(
                new LambdaQueryWrapper<KbDocumentEntity>().eq(KbDocumentEntity::getDocumentCode, id)));
        }
    }

    // ── Archive ──

    @Override
    public Optional<KbCollectionEntity> archiveCollection(String id) {
        KbCollectionEntity existing = resolveCollection(id);
        if (existing == null) return Optional.empty();
        if ("ARCHIVED".equals(existing.getStatus())) {
            return Optional.of(existing);
        }
        if (!"ACTIVE".equals(existing.getStatus())) {
            log.warn("Cannot archive collection {} with status {}", id, existing.getStatus());
            return Optional.empty();
        }
        existing.setStatus("ARCHIVED");
        collectionRepo.updateById(existing);
        log.info("Collection {} archived", id);
        return Optional.of(collectionRepo.selectById(existing.getId()));
    }

    @Override
    public Optional<KbCollectionEntity> unarchiveCollection(String id) {
        KbCollectionEntity existing = resolveCollection(id);
        if (existing == null) return Optional.empty();
        if ("ACTIVE".equals(existing.getStatus())) {
            return Optional.of(existing);
        }
        if (!"ARCHIVED".equals(existing.getStatus())) {
            log.warn("Cannot unarchive collection {} with status {}", id, existing.getStatus());
            return Optional.empty();
        }
        existing.setStatus("ACTIVE");
        collectionRepo.updateById(existing);
        log.info("Collection {} unarchived", id);
        return Optional.of(collectionRepo.selectById(existing.getId()));
    }

    private KbCollectionEntity resolveCollection(String id) {
        try {
            long numericId = Long.parseLong(id);
            return collectionRepo.selectById(numericId);
        } catch (NumberFormatException e) {
            return collectionRepo.selectOne(
                new LambdaQueryWrapper<KbCollectionEntity>().eq(KbCollectionEntity::getCollectionCode, id));
        }
    }
}
