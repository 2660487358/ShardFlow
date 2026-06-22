package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Skill 核心响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / SkillDTO.
 * <p>返回前端的核心数据结构，JSONB 字段反序列化为结构化类型便于前端消费。
 */
@Data
@NoArgsConstructor
public class SkillDTO {

    @JsonProperty("id")
    private Long id;

    @JsonProperty("skill_code")
    private String skillCode;

    @JsonProperty("skill_name")
    private String skillName;

    private String description;

    @JsonProperty("skill_type")
    private String skillType;

    @JsonProperty("trust_tier")
    private String trustTier;

    private String category;

    @JsonProperty("current_version")
    private String currentVersion;

    private String status;

    private String source;

    @JsonProperty("trigger_keywords")
    private List<String> triggerKeywords;

    @JsonProperty("input_schema")
    private Map<String, Object> inputSchema;

    @JsonProperty("output_schema")
    private Map<String, Object> outputSchema;

    @JsonProperty("cost_estimate")
    private Map<String, Object> costEstimate;

    /** Skill 运行配置，JSON 格式 */
    private Map<String, Object> config;

    private List<String> tags;

    @JsonProperty("owner_id")
    private String ownerId;

    @JsonProperty("user_id")
    private String userId;

    @JsonProperty("created_at")
    private Instant createdAt;

    @JsonProperty("updated_at")
    private Instant updatedAt;
}
