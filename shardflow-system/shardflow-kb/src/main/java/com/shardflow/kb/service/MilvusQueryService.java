package com.shardflow.kb.service;

import io.milvus.client.MilvusServiceClient;
import io.milvus.param.R;
import io.milvus.param.dml.QueryParam;
import io.milvus.grpc.QueryResults;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class MilvusQueryService {

    private final MilvusReadOnlyClient milvusClient;

    private static final String STATUS_ACTIVE = "ACTIVE";

    /**
     * Build the per-user Milvus collection name: kb_chunks_{userId}
     */
    private String userCollectionName(String userId) {
        return "kb_chunks_" + userId;
    }

    /**
     * Count distinct documents in a knowledge base by querying Milvus.
     * expr: kb_id == '{kbId}' && status == 'ACTIVE'
     */
    public long countDocuments(String userId, String kbId) {
        try {
            String collectionName = userCollectionName(userId);
            String expr = String.format("kb_id == \"%s\" && status == \"%s\"", kbId, STATUS_ACTIVE);
            R<QueryResults> resp = milvusClient.getClient().query(
                QueryParam.newBuilder()
                    .withCollectionName(collectionName)
                    .withExpr(expr)
                    .withOutFields(List.of("doc_id"))
                    .build()
            );
            if (resp.getStatus() != 0 || resp.getData() == null) {
                return 0;
            }
            return resp.getData().getFieldsDataList().stream()
                .flatMap(fd -> fd.getScalars().getStringData().getDataList().stream())
                .distinct()
                .count();
        } catch (Exception e) {
            log.warn("Milvus countDocuments failed for user={} kb={}: {}", userId, kbId, e.getMessage());
            return -1;
        }
    }

    /**
     * Count total chunks in a knowledge base.
     */
    public long countChunks(String userId, String kbId) {
        try {
            String collectionName = userCollectionName(userId);
            String expr = String.format("kb_id == \"%s\" && status == \"%s\"", kbId, STATUS_ACTIVE);
            R<QueryResults> resp = milvusClient.getClient().query(
                QueryParam.newBuilder()
                    .withCollectionName(collectionName)
                    .withExpr(expr)
                    .withOutFields(List.of("doc_id"))
                    .build()
            );
            if (resp.getStatus() != 0 || resp.getData() == null) {
                return 0;
            }
            return resp.getData().getFieldsDataList().stream()
                .flatMap(fd -> fd.getScalars().getStringData().getDataList().stream())
                .count();
        } catch (Exception e) {
            log.warn("Milvus countChunks failed for user={} kb={}: {}", userId, kbId, e.getMessage());
            return -1;
        }
    }

    /**
     * Verify that a collection/knowledge base has been fully cleaned up.
     * Returns true if NO active records exist.
     */
    public boolean verifyDeleted(String userId, String kbId) {
        long count = countChunks(userId, kbId);
        return count == 0;
    }

    /**
     * Get stats for a knowledge base: { docCount, chunkCount, exists }
     */
    public Map<String, Object> getStats(String userId, String kbId) {
        String collectionName = userCollectionName(userId);
        Map<String, Object> stats = new HashMap<>();
        stats.put("exists", milvusClient.collectionExists(collectionName));
        stats.put("docCount", countDocuments(userId, kbId));
        stats.put("chunkCount", countChunks(userId, kbId));
        return stats;
    }

    /**
     * List all kb_ids that have active data in Milvus for a specific user.
     */
    public Set<String> listActiveKbIds(String userId) {
        try {
            String collectionName = userCollectionName(userId);
            R<QueryResults> resp = milvusClient.getClient().query(
                QueryParam.newBuilder()
                    .withCollectionName(collectionName)
                    .withExpr(String.format("status == \"%s\"", STATUS_ACTIVE))
                    .withOutFields(List.of("kb_id"))
                    .withLimit(10000L)
                    .build()
            );
            if (resp.getStatus() != 0 || resp.getData() == null) {
                return Collections.emptySet();
            }
            return resp.getData().getFieldsDataList().stream()
                .flatMap(fd -> fd.getScalars().getStringData().getDataList().stream())
                .collect(Collectors.toSet());
        } catch (Exception e) {
            log.warn("Milvus listActiveKbIds failed for user={}: {}", userId, e.getMessage());
            return Collections.emptySet();
        }
    }
}
