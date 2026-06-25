package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 更新 Skill 请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-1 / IR-10 / UpdateSkillRequest.
 * <p>所有字段可选，仅更新传入字段。skill_code 不可修改。
 */
@Data
@NoArgsConstructor
public class UpdateSkillRequest {

    @Size(max = 128, message = "Skill名称最长128字符")
    @JsonProperty("skill_name")
    private String skillName;

    @Size(max = 2000, message = "Skill描述最长2000字符")
    private String description;

    @Pattern(regexp = "prompt|tool|hybrid|workflow",
             message = "skill_type 必须为 prompt/tool/hybrid/workflow")
    @JsonProperty("skill_type")
    private String skillType;

    @Pattern(regexp = "official|team|personal",
             message = "trust_tier 必须为 official/team/personal")
    @JsonProperty("trust_tier")
    private String trustTier;

    @JsonProperty("trigger_keywords")
    private List<String> triggerKeywords;

    @JsonProperty("input_schema")
    private Map<String, Object> inputSchema;

    @JsonProperty("output_schema")
    private Map<String, Object> outputSchema;

    private Map<String, Object> config;

    @JsonProperty("cost_estimate")
    private Map<String, Object> costEstimate;

    private List<String> tags;
}
