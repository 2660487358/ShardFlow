package com.shardflow.config.support;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.config.dto.CreateSkillRequest;
import com.shardflow.config.dto.SkillDetailDTO;
import com.shardflow.config.dto.SkillDTO;
import com.shardflow.config.dto.UpdateSkillRequest;
import com.shardflow.config.entity.AgentSkillBindingEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.entity.SkillVersionEntity;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Skill Entity 与 DTO 双向转换器.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / 实施计划 P2.2.
 * <p>职责：
 * <ul>
 *   <li>Entity → SkillDTO / SkillDetailDTO（含 JSONB 反序列化）</li>
 *   <li>CreateSkillRequest → Entity（含 JSONB 序列化）</li>
 *   <li>UpdateSkillRequest → Entity（选择性合并，仅更新非 null 字段）</li>
 * </ul>
 *
 * <p>JSONB 字段在 Entity 中为 String 类型，DTO 中为结构化类型（List/Map）。
 * 使用 ObjectMapper 手动序列化/反序列化，与 MCP/KB 模块模式一致。
 * 反序列化失败降级返回空集合，不抛异常。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SkillEntityConverter {

    private final ObjectMapper objectMapper;

    // ======================== Entity → DTO ========================

    /**
     * Entity 转 SkillDTO，自动反序列化 JSONB 字段.
     */
    public SkillDTO toDTO(SkillRegistryEntity entity) {
        SkillDTO dto = new SkillDTO();
        copyBaseFields(entity, dto);
        dto.setTriggerKeywords(parseStringList(entity.getTriggerKeywords()));
        dto.setInputSchema(parseObjectMap(entity.getInputSchema()));
        dto.setOutputSchema(parseObjectMap(entity.getOutputSchema()));
        dto.setCostEstimate(parseObjectMap(entity.getCostEstimate()));
        dto.setConfig(parseObjectMap(entity.getConfig()));
        dto.setTags(parseStringList(entity.getTags()));
        return dto;
    }

    /**
     * 构建 SkillDetailDTO（含关联 Agent 列表和版本历史）.
     *
     * @param entity   Skill 实体
     * @param bindings Agent-Skill 绑定列表
     * @param versions 版本历史列表
     * @return SkillDetailDTO
     */
    public SkillDetailDTO toDetailDTO(SkillRegistryEntity entity,
                                      List<AgentSkillBindingEntity> bindings,
                                      List<SkillVersionEntity> versions) {
        SkillDetailDTO dto = new SkillDetailDTO();
        copyBaseFields(entity, dto);
        dto.setTriggerKeywords(parseStringList(entity.getTriggerKeywords()));
        dto.setInputSchema(parseObjectMap(entity.getInputSchema()));
        dto.setOutputSchema(parseObjectMap(entity.getOutputSchema()));
        dto.setCostEstimate(parseObjectMap(entity.getCostEstimate()));
        dto.setConfig(parseObjectMap(entity.getConfig()));
        dto.setTags(parseStringList(entity.getTags()));

        dto.setAgents(bindings.stream()
            .map(this::toAgentRef)
            .collect(Collectors.toList()));

        dto.setVersions(versions.stream()
            .map(this::toVersionRef)
            .collect(Collectors.toList()));

        return dto;
    }

    // ======================== Request → Entity ========================

    /**
     * 从 CreateSkillRequest 构建 Entity.
     *
     * @param request 创建请求
     * @param userId  当前用户ID
     * @return SkillRegistryEntity（未持久化）
     */
    public SkillRegistryEntity fromCreateRequest(CreateSkillRequest request, String userId) {
        SkillRegistryEntity entity = new SkillRegistryEntity();
        entity.setSkillName(request.getSkillName());
        entity.setDescription(request.getDescription());
        entity.setSkillType(request.getSkillType() != null ? request.getSkillType() : "prompt");
        entity.setTrustTier(request.getTrustTier() != null ? request.getTrustTier() : "personal");
        entity.setCategory(request.getCategory() != null ? request.getCategory() : "");
        entity.setSource("CUSTOM");
        entity.setStatus("draft");
        entity.setOwnerId(userId);
        entity.setUserId(userId);
        entity.setCreatedBy(userId);
        entity.setUpdatedBy(userId);
        // JSONB 序列化
        entity.setCurrentVersion("");
        entity.setTriggerKeywords(toJsonString(request.getTriggerKeywords()));
        entity.setInputSchema(toJsonString(request.getInputSchema()));
        entity.setOutputSchema(toJsonString(request.getOutputSchema()));
        entity.setCostEstimate(toJsonString(request.getCostEstimate()));
        entity.setConfig(toJsonString(request.getConfig()));
        entity.setTags(toJsonString(request.getTags()));
        return entity;
    }

    /**
     * 选择性合并更新（仅更新 request 中非 null 的字段）.
     *
     * @param entity  已存在的 Entity（将被修改）
     * @param request 更新请求
     */
    public void mergeUpdates(SkillRegistryEntity entity, UpdateSkillRequest request) {
        if (request.getSkillName() != null) entity.setSkillName(request.getSkillName());
        if (request.getDescription() != null) entity.setDescription(request.getDescription());
        if (request.getSkillType() != null) entity.setSkillType(request.getSkillType());
        if (request.getTrustTier() != null) entity.setTrustTier(request.getTrustTier());
        if (request.getCategory() != null) entity.setCategory(request.getCategory());
        // JSONB 字段选择性更新
        if (request.getTriggerKeywords() != null) {
            entity.setTriggerKeywords(toJsonString(request.getTriggerKeywords()));
        }
        if (request.getInputSchema() != null) {
            entity.setInputSchema(toJsonString(request.getInputSchema()));
        }
        if (request.getOutputSchema() != null) {
            entity.setOutputSchema(toJsonString(request.getOutputSchema()));
        }
        if (request.getCostEstimate() != null) {
            entity.setCostEstimate(toJsonString(request.getCostEstimate()));
        }
        if (request.getConfig() != null) {
            entity.setConfig(toJsonString(request.getConfig()));
        }
        if (request.getTags() != null) {
            entity.setTags(toJsonString(request.getTags()));
        }
    }

    // ======================== 内部转换方法 ========================

    private SkillDetailDTO.AgentRef toAgentRef(AgentSkillBindingEntity binding) {
        SkillDetailDTO.AgentRef ref = new SkillDetailDTO.AgentRef();
        ref.setId(binding.getId());
        ref.setAgentCode(binding.getAgentId());
        ref.setBindingType(binding.getBindingType());
        ref.setPriority(binding.getPriority());
        // name 暂时设为 agentId，P4 阶段可关联查询 agent_config 获取真实名称
        ref.setName(binding.getAgentId());
        return ref;
    }

    private SkillDetailDTO.VersionRef toVersionRef(SkillVersionEntity version) {
        SkillDetailDTO.VersionRef ref = new SkillDetailDTO.VersionRef();
        ref.setVersionTag(version.getVersionTag());
        ref.setStatus(version.getStatus());
        ref.setChangeLog(version.getChangeLog());
        ref.setPromotedBy(version.getPromotedBy());
        ref.setPromotedAt(version.getPromotedAt());
        return ref;
    }

    private void copyBaseFields(SkillRegistryEntity entity, SkillDTO dto) {
        dto.setId(entity.getId());
        dto.setSkillCode(entity.getSkillCode());
        dto.setSkillName(entity.getSkillName());
        dto.setDescription(entity.getDescription());
        dto.setSkillType(entity.getSkillType());
        dto.setTrustTier(entity.getTrustTier());
        dto.setCategory(entity.getCategory());
        dto.setCurrentVersion(entity.getCurrentVersion());
        dto.setStatus(entity.getStatus());
        dto.setSource(entity.getSource());
        dto.setOwnerId(entity.getOwnerId());
        dto.setUserId(entity.getUserId());
        dto.setCreatedAt(entity.getCreatedAt());
        dto.setUpdatedAt(entity.getUpdatedAt());
    }

    // ======================== JSONB 序列化/反序列化 ========================

    private List<String> parseStringList(String json) {
        if (json == null || json.isBlank()) return List.of();
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {});
        } catch (Exception e) {
            log.warn("Failed to parse JSON string list: {}", json, e);
            return List.of();
        }
    }

    private Map<String, Object> parseObjectMap(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.warn("Failed to parse JSON object map: {}", json, e);
            return Map.of();
        }
    }

    private String toJsonString(Object obj) {
        if (obj == null) return null;
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.warn("Failed to serialize to JSON: {}", obj, e);
            return null;
        }
    }
}
