package com.shardflow.kb.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.KbCollectionEntity;
import com.shardflow.kb.repository.KbCollectionRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

@Slf4j
@Service
@EnableScheduling
@RequiredArgsConstructor
public class ReconciliationService {

    private final KbCollectionRepository collectionRepo;
    private final MilvusQueryService milvusQueryService;

    /**
     * Daily reconciliation at 2:00 AM.
     * Compares MySQL doc_count/chunk_count with Milvus actual data.
     */
    @Scheduled(cron = "0 0 2 * * ?")
    public void scheduledReconciliation() {
        log.info("Starting daily Milvus-MySQL reconciliation...");
        List<KbCollectionEntity> activeColls = collectionRepo.selectList(
            new LambdaQueryWrapper<KbCollectionEntity>()
                .eq(KbCollectionEntity::getStatus, "ACTIVE")
        );

        int mismatchCount = 0;
        for (KbCollectionEntity coll : activeColls) {
            Map<String, Object> milvusStats = milvusQueryService.getStats(coll.getUserId(), coll.getCollectionCode());
            long milvusDocCount = (long) milvusStats.getOrDefault("docCount", -1L);
            long milvusChunkCount = (long) milvusStats.getOrDefault("chunkCount", -1L);

            if (milvusDocCount < 0 || milvusChunkCount < 0) {
                log.warn("RECONCILE: kb={} name={} Milvus query failed", coll.getCollectionCode(), coll.getName());
                continue;
            }

            long mysqlDoc = coll.getDocCount() != null ? coll.getDocCount() : 0;
            long mysqlChunk = coll.getChunkCount() != null ? coll.getChunkCount() : 0;

            double docDiff = mysqlDoc > 0 ? Math.abs(milvusDocCount - mysqlDoc) / (double) mysqlDoc : 0;
            double chunkDiff = mysqlChunk > 0 ? Math.abs(milvusChunkCount - mysqlChunk) / (double) mysqlChunk : 0;

            if (docDiff > 0.05 || chunkDiff > 0.05) {
                mismatchCount++;
                log.warn("RECONCILE MISMATCH: kb={} name={} mysql:[docs={}, chunks={}] milvus:[docs={}, chunks={}]",
                    coll.getCollectionCode(), coll.getName(),
                    mysqlDoc, mysqlChunk,
                    milvusDocCount, milvusChunkCount);
            }
        }

        log.info("Reconciliation complete: {} collections checked, {} mismatches detected (>5%)",
            activeColls.size(), mismatchCount);
    }

    /**
     * Manual trigger reconciliation via API.
     */
    public int reconcileNow() {
        log.info("Manual reconciliation triggered...");
        scheduledReconciliation();
        return 0;
    }
}
