package com.shardflow.strategy.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.strategy.*;
import com.shardflow.common.entity.StrategyRecordEntity;
import com.shardflow.strategy.repository.StrategyRecordRepository;
import com.shardflow.strategy.service.StrategyRecordService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class StrategyRecordServiceImpl implements StrategyRecordService {

    private final StrategyRecordRepository strategyRepository;
    private final ObjectMapper objectMapper;

    private static final BigDecimal MIN_SUCCESS_SCORE = BigDecimal.ZERO;
    private static final BigDecimal MAX_SUCCESS_SCORE = BigDecimal.ONE;
    private static final BigDecimal FEEDBACK_USEFUL_BONUS = new BigDecimal("0.05");
    private static final BigDecimal FEEDBACK_NEGATIVE_PENALTY = new BigDecimal("0.10");

    @Override
    @Transactional
    public StrategyCreateResponse createStrategy(StrategyCreateRequest request) {
        StrategyRecordEntity entity = new StrategyRecordEntity();

        // Generate record ID if not provided
        if (request.getRecordId() == null || request.getRecordId().isBlank()) {
            entity.setRecordId("sr-" + UUID.randomUUID().toString().replace("-", "").substring(0, 12));
        } else {
            entity.setRecordId(request.getRecordId());
        }

        entity.setUserId(request.getUserId());
        entity.setTaskType(request.getTaskType());
        entity.setQueryPattern(request.getQueryPattern());

        // Serialize tool_combo to JSON string
        entity.setToolCombo(toJson(request.getToolCombo()));

        // Serialize user_feedback to JSON string
        entity.setUserFeedback(toJson(request.getUserFeedback()));

        // Set success score
        BigDecimal successScore = request.getSuccessScore() != null
                ? BigDecimal.valueOf(request.getSuccessScore())
                : BigDecimal.ZERO;
        entity.setSuccessScore(successScore);

        entity.setCostMs(request.getCostMs());
        entity.setIsDeleted(false);
        entity.setCreatedAt(Instant.now());

        strategyRepository.insert(entity);

        log.info("Strategy created: recordId={}, user={}, type={}, score={}",
                entity.getRecordId(), entity.getUserId(), entity.getTaskType(), entity.getSuccessScore());

        return StrategyCreateResponse.created(entity.getRecordId(), entity.getSuccessScore().doubleValue());
    }

    @Override
    public Optional<StrategySearchResponse.StrategyResultItem> getStrategy(String recordId) {
        StrategyRecordEntity entity = strategyRepository.selectOne(
                new LambdaQueryWrapper<StrategyRecordEntity>()
                        .eq(StrategyRecordEntity::getRecordId, recordId)
                        .eq(StrategyRecordEntity::getIsDeleted, false));

        if (entity == null) {
            return Optional.empty();
        }

        return Optional.of(toResultItem(entity));
    }

    @Override
    @Transactional
    public boolean deleteStrategy(String recordId) {
        int updated = strategyRepository.update(null,
                new LambdaUpdateWrapper<StrategyRecordEntity>()
                        .eq(StrategyRecordEntity::getRecordId, recordId)
                        .set(StrategyRecordEntity::getIsDeleted, true));

        if (updated > 0) {
            log.info("Strategy soft-deleted: recordId={}", recordId);
            return true;
        }
        return false;
    }

    @Override
    @SuppressWarnings("unchecked")
    public StrategySearchResponse searchStrategy(StrategySearchRequest request) {
        long startTime = System.currentTimeMillis();

        LambdaQueryWrapper<StrategyRecordEntity> wrapper = new LambdaQueryWrapper<StrategyRecordEntity>()
                .eq(StrategyRecordEntity::getIsDeleted, false);

        // Filter by user_id
        if (request.getUserId() != null && !request.getUserId().isBlank()) {
            wrapper.eq(StrategyRecordEntity::getUserId, request.getUserId());
        }

        // Filter by task_type
        if (request.getTaskType() != null && !request.getTaskType().isBlank()) {
            wrapper.eq(StrategyRecordEntity::getTaskType, request.getTaskType());
        }

        // Order by success_score descending, then by created_at descending
        wrapper.orderByDesc(StrategyRecordEntity::getSuccessScore)
               .orderByDesc(StrategyRecordEntity::getCreatedAt);

        // Limit results
        int limit = request.getTopK() != null ? request.getTopK() : 3;
        wrapper.last("LIMIT " + Math.min(limit, 50));

        List<StrategyRecordEntity> entities = strategyRepository.selectList(wrapper);

        // Convert to result items
        List<StrategySearchResponse.StrategyResultItem> results = entities.stream()
                .map(this::toResultItem)
                .collect(Collectors.toList());

        long elapsedMs = System.currentTimeMillis() - startTime;

        StrategySearchResponse response = new StrategySearchResponse();
        response.setResults(results);
        response.setTotal(results.size());
        response.setSearchTimeMs(elapsedMs);

        return response;
    }

    @Override
    @Transactional
    public Map<String, Object> applyFeedback(StrategyFeedbackRequest request) {
        StrategyRecordEntity entity = strategyRepository.selectOne(
                new LambdaQueryWrapper<StrategyRecordEntity>()
                        .eq(StrategyRecordEntity::getRecordId, request.getRecordId())
                        .eq(StrategyRecordEntity::getIsDeleted, false));

        if (entity == null) {
            return Map.of("success", false, "error", "Strategy not found");
        }

        // Calculate score delta
        BigDecimal delta;
        if ("useful".equals(request.getFeedback())) {
            delta = FEEDBACK_USEFUL_BONUS;
        } else if ("not_relevant".equals(request.getFeedback())) {
            delta = FEEDBACK_NEGATIVE_PENALTY.negate();
        } else {
            return Map.of("success", false, "error", "Invalid feedback type");
        }

        // Override with provided score_delta if present
        if (request.getScoreDelta() != null) {
            delta = BigDecimal.valueOf(request.getScoreDelta());
        }

        // Update success_score
        BigDecimal newScore = entity.getSuccessScore()
                .add(delta)
                .max(MIN_SUCCESS_SCORE)
                .min(MAX_SUCCESS_SCORE);

        // Update user_feedback JSON
        Map<String, String> feedback = parseJsonToMap(entity.getUserFeedback());
        if (request.getToolName() != null) {
            feedback.put(request.getToolName(), request.getFeedback());
        }

        strategyRepository.update(null,
                new LambdaUpdateWrapper<StrategyRecordEntity>()
                        .eq(StrategyRecordEntity::getRecordId, request.getRecordId())
                        .set(StrategyRecordEntity::getSuccessScore, newScore)
                        .set(StrategyRecordEntity::getUserFeedback, toJson(feedback)));

        log.info("Feedback applied: recordId={}, tool={}, feedback={}, newScore={}",
                request.getRecordId(), request.getToolName(), request.getFeedback(), newScore);

        return Map.of(
                "success", true,
                "record_id", request.getRecordId(),
                "new_success_score", newScore.doubleValue()
        );
    }

    @Override
    @Transactional
    @SuppressWarnings("unchecked")
    public StrategyCreateResponse saveFromCallback(Map<String, Object> body) {
        StrategyCreateRequest request = new StrategyCreateRequest();

        request.setRecordId((String) body.get("record_id"));
        request.setUserId((String) body.get("user_id"));
        request.setTaskType((String) body.get("task_type"));
        request.setQueryPattern((String) body.get("query_pattern"));

        // Parse tool_combo
        Object toolComboObj = body.get("tool_combo");
        if (toolComboObj instanceof List) {
            List<Map<String, Object>> comboList = (List<Map<String, Object>>) toolComboObj;
            List<StrategyCreateRequest.ToolComboItem> items = comboList.stream()
                    .map(m -> {
                        StrategyCreateRequest.ToolComboItem item = new StrategyCreateRequest.ToolComboItem();
                        item.setTool((String) m.getOrDefault("tool", ""));
                        item.setWeight(m.get("weight") instanceof Number
                                ? ((Number) m.get("weight")).doubleValue() : 0.0);
                        item.setReliability(m.get("reliability") instanceof Number
                                ? ((Number) m.get("reliability")).doubleValue() : 0.0);
                        return item;
                    })
                    .collect(Collectors.toList());
            request.setToolCombo(items);
        }

        // Parse user_feedback
        Object feedbackObj = body.get("user_feedback");
        if (feedbackObj instanceof Map) {
            request.setUserFeedback((Map<String, String>) feedbackObj);
        }

        // Parse success_score
        Object scoreObj = body.get("success_score");
        if (scoreObj instanceof Number) {
            request.setSuccessScore(((Number) scoreObj).doubleValue());
        }

        // Parse cost_ms
        Object costObj = body.get("cost_ms");
        if (costObj instanceof Number) {
            request.setCostMs(((Number) costObj).intValue());
        }

        // Check if record already exists (upsert)
        if (request.getRecordId() != null && !request.getRecordId().isBlank()) {
            StrategyRecordEntity existing = strategyRepository.selectOne(
                    new LambdaQueryWrapper<StrategyRecordEntity>()
                            .eq(StrategyRecordEntity::getRecordId, request.getRecordId())
                            .eq(StrategyRecordEntity::getIsDeleted, false));

            if (existing != null) {
                // Update existing record
                return updateExistingStrategy(existing, request);
            }
        }

        return createStrategy(request);
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    private StrategyCreateResponse updateExistingStrategy(
            StrategyRecordEntity entity, StrategyCreateRequest request) {
        if (request.getToolCombo() != null) {
            entity.setToolCombo(toJson(request.getToolCombo()));
        }
        if (request.getUserFeedback() != null) {
            entity.setUserFeedback(toJson(request.getUserFeedback()));
        }
        if (request.getSuccessScore() != null) {
            entity.setSuccessScore(BigDecimal.valueOf(request.getSuccessScore()));
        }
        if (request.getCostMs() != null) {
            entity.setCostMs(request.getCostMs());
        }

        strategyRepository.updateById(entity);

        log.info("Strategy updated via callback: recordId={}", entity.getRecordId());

        StrategyCreateResponse response = new StrategyCreateResponse();
        response.setRecordId(entity.getRecordId());
        response.setStatus("updated");
        response.setSuccessScore(entity.getSuccessScore().doubleValue());
        return response;
    }

    private StrategySearchResponse.StrategyResultItem toResultItem(StrategyRecordEntity entity) {
        StrategySearchResponse.StrategyResultItem item = new StrategySearchResponse.StrategyResultItem();
        item.setRecordId(entity.getRecordId());
        item.setTaskType(entity.getTaskType());
        item.setQueryPattern(entity.getQueryPattern());
        item.setSuccessScore(entity.getSuccessScore() != null ? entity.getSuccessScore().doubleValue() : 0.0);

        // Parse tool_combo JSON string to List<Map>
        try {
            if (entity.getToolCombo() != null && !entity.getToolCombo().isBlank()) {
                List<Map<String, Object>> comboList = objectMapper.readValue(
                        entity.getToolCombo(),
                        objectMapper.getTypeFactory().constructCollectionType(List.class, Map.class));
                item.setToolCombo(comboList);
            }
        } catch (JsonProcessingException e) {
            log.warn("Failed to parse tool_combo JSON for record {}: {}", entity.getRecordId(), e.getMessage());
            item.setToolCombo(List.of());
        }

        return item;
    }

    private String toJson(Object obj) {
        if (obj == null) {
            return null;
        }
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            log.warn("Failed to serialize object to JSON", e);
            return "{}";
        }
    }

    @SuppressWarnings("unchecked")
    private Map<String, String> parseJsonToMap(String json) {
        if (json == null || json.isBlank()) {
            return new HashMap<>();
        }
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (JsonProcessingException e) {
            log.warn("Failed to parse JSON to Map: {}", e.getMessage());
            return new HashMap<>();
        }
    }
}
