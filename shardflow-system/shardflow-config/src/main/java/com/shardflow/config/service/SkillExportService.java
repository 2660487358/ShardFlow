package com.shardflow.config.service;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.*;

/**
 * Skill 导出服务.
 *
 * <p>Per Skills管理需求规格文档 FR-3.4 / FR-3.5 / 实施计划 P3.4.
 * <p>支持按 ID 批量导出 Skill 完整定义，返回 JSON 数组。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillExportService {

    private final SkillRegistryRepository skillRegistryRepo;
    private final SkillPermissionChecker permissionChecker;
    private final ObjectMapper objectMapper;

    /**
     * 导出指定 ID 列表的 Skill 定义.
     * FR-3.4 / P3.4.1: GET /api/v1/skills/export?ids=...
     *
     * @param ids Skill ID 列表
     * @return 包含一个或多个 Skill 定义的 JSON 数组字符串
     */
    public String exportSkills(List<Long> ids) {
        if (ids == null || ids.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Export ids are required");
        }

        String userId = UserContext.getUserId();
        List<Map<String, Object>> exportList = new ArrayList<>();

        for (Long id : ids) {
            SkillRegistryEntity entity = skillRegistryRepo.selectById(id);
            if (entity == null) {
                log.warn("Skip export: skill not found, id={}", id);
                continue;
            }

            // 权限校验：仅允许导出自己拥有的 Skill 或 official Skill
            permissionChecker.checkReadPermission(userId, entity);

            exportList.add(toExportMap(entity));
        }

        if (exportList.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No skills found for export");
        }

        try {
            return objectMapper.writeValueAsString(exportList);
        } catch (Exception e) {
            log.error("Failed to serialize export skills", e);
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR,
                "Failed to serialize export result", e);
        }
    }

    /**
     * P3.4.2: 导出完整 Skill 定义.
     */
    private Map<String, Object> toExportMap(SkillRegistryEntity entity) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("skill_code", entity.getSkillCode());
        map.put("skill_name", entity.getSkillName());
        map.put("description", entity.getDescription());
        map.put("skill_type", entity.getSkillType());
        map.put("trust_tier", entity.getTrustTier());
        map.put("category", entity.getCategory());
        map.put("status", entity.getStatus());
        map.put("current_version", entity.getCurrentVersion());
        map.put("source", entity.getSource());
        map.put("trigger_keywords", parseJsonList(entity.getTriggerKeywords()));
        map.put("input_schema", parseJsonMap(entity.getInputSchema()));
        map.put("output_schema", parseJsonMap(entity.getOutputSchema()));
        map.put("config", parseJsonMap(entity.getConfig()));
        map.put("cost_estimate", parseJsonMap(entity.getCostEstimate()));
        map.put("tags", parseJsonList(entity.getTags()));
        map.put("owner_id", entity.getOwnerId());
        map.put("created_at", entity.getCreatedAt());
        map.put("updated_at", entity.getUpdatedAt());
        return map;
    }

    private List<String> parseJsonList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {});
        } catch (Exception e) {
            return List.of();
        }
    }

    private Map<String, Object> parseJsonMap(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            return Map.of();
        }
    }
}
