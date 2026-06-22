package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Skill 导入请求 DTO（解析后的结构）.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / FR-3.
 * <p>导入接口接收 multipart/form-data JSON 文件，解析后可为单对象或数组。
 * 该 DTO 表示单个 Skill 导入条目，与 CreateSkillRequest 字段对齐但无校验注解
 * （导入需逐条校验并收集错误，校验失败记录到 ImportResult.details）。
 */
@Data
@NoArgsConstructor
public class SkillImportRequest {

    @JsonProperty("skill_name")
    private String skillName;

    private String description;

    @JsonProperty("skill_type")
    private String skillType;

    @JsonProperty("trust_tier")
    private String trustTier;

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

    private Map<String, String> artifacts;
}
