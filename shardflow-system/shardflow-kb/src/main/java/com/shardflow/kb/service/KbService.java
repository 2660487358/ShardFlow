package com.shardflow.kb.service;

import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.common.entity.KbDocumentEntity;
import java.util.List;
import java.util.Optional;

public interface KbService {

    // Collections
    List<KbCollectionEntity> listCollections(String userId);
    Optional<KbCollectionEntity> getCollection(String id);
    KbCollectionEntity createCollection(KbCollectionEntity collection);
    Optional<KbCollectionEntity> updateCollection(String id, KbCollectionEntity updates);
    boolean deleteCollection(String id);

    // Documents
    List<KbDocumentEntity> listDocuments(String collectionId);
    KbDocumentEntity addDocument(KbDocumentEntity doc);
    boolean deleteDocument(String id);
}
