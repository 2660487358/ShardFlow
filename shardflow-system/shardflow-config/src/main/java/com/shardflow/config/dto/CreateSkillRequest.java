package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 创建 Skill 请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-1 / IR-10 / CreateSkillRequest.
 * <p>字段校验：name ≤ 128，description ≤ 2000（NFR-5.4）。
 * skill_code 由后端自动生成（DR-4），请求体不接收。
 */
@Data
@NoArgsConstructor
public class CreateSkillRequest {

    @NotBlank(message = "Skill名称不能为空")
    @Size(max = 128, message = "Skill名称最长128字符")
    @JsonProperty("skill_name")
    private String skillName;

    @Size(max = 2000, message = "Skill描述最长2000字符")
    private String description;

    @Pattern(regexp = "prompt|tool|hybrid|workflow",
             message = "skill_type 必须为 prompt/tool/hybrid/workflow")
    @JsonProperty("skill_type")
    private String skillType = "prompt";

    @Pattern(regexp = "official|team|personal",
             message = "trust_tier 必须为 official/team/personal")
    @JsonProperty("trust_tier")
    private String trustTier = "personal";

    private String category;

    @JsonProperty("trigger_keywords")
    private List<String> triggerKeywords;

    @JsonProperty("input_schema")
    private Map<String, Object> inputSchema;

    @JsonProperty("output_schema")
    private Map<String, Object> outputSchema;

    /** Skill 运行配置，JSON 格式 */
    private Map<String, Object> config;

    @JsonProperty("cost_estimate")
    private Map<String, Object> costEstimate;

    private List<String> tags;

    /** Artifact 文件引用，如 {"prompt": "prompt.md", "tool_handler": "tool.py"} */
    private Map<String, String> artifacts;
}
