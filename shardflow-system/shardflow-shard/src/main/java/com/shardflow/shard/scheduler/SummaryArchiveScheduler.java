package com.shardflow.shard.scheduler;

import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.session.SessionSummaryCreateRequest;
import com.shardflow.common.dto.session.SessionSummaryCreateResponse;
import com.shardflow.common.entity.SessionStateSummaryEntity;
import com.shardflow.shard.service.SessionStateSummaryService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.Optional;

/**
 * 会话状态摘要归档调度器（C-3.4 三级读取路径 L1→L2）。
 * <p>
 * 规则条款：C-3.4（会话状态摘要三级存取）、C-4.9（L1→L2 异步归档）、C-6.5（版本号乐观锁）、C-8.4（TTL 管理）。
 * <p>
 * 工作流程：
 * 1. 定时扫描 Redis 中 {@code session:*:summary} 键（使用 SCAN，禁止 KEYS，C-8.5）。
 * 2. 解析摘要 JSON，提取 user_id/task_id/version。
 * 3. 与 PG L2 中最新版本比较，仅当归略版本更高时执行归档（C-6.5 乐观锁）。
 * 4. 归档成功后保留 Redis 副本（供 L1 读取），不主动删除（由 TTL 自然过期）。
 * 5. 记录归档审计日志，便于追踪。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SummaryArchiveScheduler {

    private final RedisTemplate<String, Object> redisTemplate;
    private final SessionStateSummaryService summaryService;
    private final ObjectMapper objectMapper;

    /** Redis Key 模式：session:{session_id}:summary */
    private static final String REDIS_KEY_PATTERN = "session:*:summary";

    /** 单次扫描最大数量，避免阻塞 Redis */
    private static final int BATCH_SIZE = 200;

    /** SCAN 游标匹配数 */
    private static final long SCAN_COUNT = 100L;

    /**
     * 每 60 秒执行一次归档扫描。
     * <p>
     * 使用 fixedDelay 而非 fixedRate，确保前一次执行完成后才开始下一次，避免堆积。
     */
    @Scheduled(fixedDelay = 60_000L, initialDelay = 30_000L)
    public void archiveSummaries() {
        long start = System.currentTimeMillis();
        int scanned = 0;
        int archived = 0;
        int skipped = 0;
        int failed = 0;

        try (Cursor<byte[]> cursor = redisTemplate.getConnectionFactory()
                .getConnection()
                .keyCommands()
                .scan(ScanOptions.scanOptions()
                        .match(REDIS_KEY_PATTERN)
                        .count(SCAN_COUNT)
                        .build())) {

            while (cursor.hasNext() && scanned < BATCH_SIZE) {
                scanned++;
                String key = new String(cursor.next());
                try {
                    ArchiveResult result = archiveOne(key);
                    switch (result) {
                        case ARCHIVED -> archived++;
                        case SKIPPED -> skipped++;
                        case FAILED -> failed++;
                    }
                } catch (Exception e) {
                    log.warn("Failed to archive summary key={}: {}", key, e.getMessage());
                    failed++;
                }
            }
        } catch (Exception e) {
            log.error("Summary archive scan failed: {}", e.getMessage(), e);
        }

        long elapsed = System.currentTimeMillis() - start;
        log.info("Summary archive scan completed: scanned={}, archived={}, skipped={}, failed={}, elapsed={}ms",
                scanned, archived, skipped, failed, elapsed);
    }

    /**
     * 归档单个 Redis 摘要到 PG。
     */
    private ArchiveResult archiveOne(String redisKey) {
        // 解析 session_id from key: session:{session_id}:summary
        String sessionId = extractSessionId(redisKey);
        if (sessionId == null) {
            log.debug("Skip non-summary key: {}", redisKey);
            return ArchiveResult.SKIPPED;
        }

        Object raw = redisTemplate.opsForValue().get(redisKey);
        if (raw == null) {
            return ArchiveResult.SKIPPED;
        }

        try {
            String json = (raw instanceof String s) ? s : objectMapper.writeValueAsString(raw);
            if (json == null || json.isBlank()) {
                log.debug("Skip empty summary content: key={}", redisKey);
                return ArchiveResult.SKIPPED;
            }

            @SuppressWarnings("unchecked")
            Map<String, Object> summaryMap = objectMapper.readValue(json, Map.class);

            String userId = (String) summaryMap.get("user_id");
            String taskId = (String) summaryMap.get("task_id");
            Object versionObj = summaryMap.get("version");
            int redisVersion = (versionObj instanceof Number n) ? n.intValue() : 0;

            if (userId == null || taskId == null) {
                log.debug("Skip summary without user_id/task_id: key={}", redisKey);
                return ArchiveResult.SKIPPED;
            }

            // 检查 PG L2 中是否已有更高或相同版本（C-6.5 乐观锁）
            Optional<SessionStateSummaryEntity> existingOpt =
                    summaryService.getLatestByUserAndTask(userId, taskId);
            if (existingOpt.isPresent()) {
                int pgVersion = existingOpt.get().getVersion() != null ? existingOpt.get().getVersion() : 0;
                if (pgVersion >= redisVersion) {
                    log.debug("Skip archive (PG version {} >= Redis version {}): user={}, task={}",
                            pgVersion, redisVersion, userId, taskId);
                    return ArchiveResult.SKIPPED;
                }
            }

            // 构造归档请求
            SessionSummaryCreateRequest request = buildArchiveRequest(summaryMap);

            // 执行归档
            SessionSummaryCreateResponse response = summaryService.saveFromCallback(request);
            log.info("Summary archived: user={}, task={}, session={}, summaryId={}, status={}",
                    userId, taskId, sessionId, response.getSummaryId(), response.getStatus());
            return ArchiveResult.ARCHIVED;

        } catch (Exception e) {
            log.warn("Failed to parse/archive summary key={}: {}", redisKey, e.getMessage());
            return ArchiveResult.FAILED;
        }
    }

    /**
     * 从 Redis Key 提取 session_id。
     * Key 格式：session:{session_id}:summary
     */
    private String extractSessionId(String key) {
        // 去掉可能的前缀（如有 namespace）
        String[] parts = key.split(":");
        // 期望格式：["session", "{sessionId}", "summary"]
        if (parts.length >= 3 && "session".equals(parts[0]) && "summary".equals(parts[parts.length - 1])) {
            return parts[1];
        }
        return null;
    }

    /**
     * 从 Redis 摘要 Map 构造归档请求。
     */
    @SuppressWarnings("unchecked")
    private SessionSummaryCreateRequest buildArchiveRequest(Map<String, Object> summaryMap) {
        SessionSummaryCreateRequest request = new SessionSummaryCreateRequest();
        request.setUserId((String) summaryMap.get("user_id"));
        request.setTaskId((String) summaryMap.get("task_id"));
        request.setTaskType((String) summaryMap.get("task_type"));
        request.setTaskGoal((String) summaryMap.get("task_goal"));
        request.setCompressedHistory((String) summaryMap.get("compressed_history"));

        Object seqObj = summaryMap.get("session_seq");
        if (seqObj instanceof Number n) {
            request.setSessionSeq(n.intValue());
        }

        // knowledge_state
        Object ksObj = summaryMap.get("knowledge_state");
        if (ksObj instanceof Map) {
            Map<String, Object> ksMap = (Map<String, Object>) ksObj;
            SessionSummaryCreateRequest.KnowledgeState ks = new SessionSummaryCreateRequest.KnowledgeState();
            ks.setConfirmed((java.util.List<String>) ksMap.getOrDefault("confirmed", java.util.List.of()));
            ks.setExcluded((java.util.List<String>) ksMap.getOrDefault("excluded", java.util.List.of()));
            ks.setPending((java.util.List<String>) ksMap.getOrDefault("pending", java.util.List.of()));
            request.setKnowledgeState(ks);
        }

        // user_context
        Object ucObj = summaryMap.get("user_context");
        if (ucObj instanceof Map) {
            Map<String, Object> ucMap = (Map<String, Object>) ucObj;
            SessionSummaryCreateRequest.UserContext uc = new SessionSummaryCreateRequest.UserContext();
            uc.setExpertiseLevel((String) ucMap.getOrDefault("expertise_level", ""));
            uc.setPreferredDepth((String) ucMap.getOrDefault("preferred_depth", ""));
            uc.setCommunicationStyle((String) ucMap.getOrDefault("communication_style", ""));
            request.setUserContext(uc);
        }

        // execution_state
        Object esObj = summaryMap.get("execution_state");
        if (esObj instanceof Map) {
            Map<String, Object> esMap = (Map<String, Object>) esObj;
            SessionSummaryCreateRequest.ExecutionState es = new SessionSummaryCreateRequest.ExecutionState();
            Object stepsObj = esMap.get("completed_steps");
            if (stepsObj instanceof Number n) es.setCompletedSteps(n.intValue());
            es.setCurrentStep((String) esMap.getOrDefault("current_step", ""));
            es.setToolsUsed((java.util.List<String>) esMap.getOrDefault("tools_used", java.util.List.of()));
            es.setEstimatedRemaining((String) esMap.getOrDefault("estimated_remaining", ""));
            request.setExecutionState(es);
        }

        // source_preference
        Object spObj = summaryMap.get("source_preference");
        if (spObj instanceof Map) {
            Map<String, Double> sp = (Map<String, Double>) spObj;
            request.setSourcePreference(sp);
        }

        return request;
    }

    private enum ArchiveResult {
        ARCHIVED, SKIPPED, FAILED
    }
}
