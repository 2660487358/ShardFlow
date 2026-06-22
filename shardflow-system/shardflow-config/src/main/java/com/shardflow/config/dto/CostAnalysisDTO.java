package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * Skill 成本分析响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / CostAnalysisDTO / FR-8.8.
 * <p>按 Skill 统计 Token 消耗、调用次数、延迟与成本，支持 30 天内查询。
 */
@Data
@NoArgsConstructor
public class CostAnalysisDTO {

    @JsonProperty("skill_id")
    private Long skillId;

    @JsonProperty("skill_code")
    private String skillCode;

    @JsonProperty("skill_name")
    private String skillName;

    /** 调用次数 */
    @JsonProperty("call_count")
    private Long callCount;

    /** 成功调用次数 */
    @JsonProperty("success_count")
    private Long successCount;

    /** 失败调用次数 */
    @JsonProperty("failure_count")
    private Long failureCount;

    /** 总输入 Token 消耗 */
    @JsonProperty("total_input_tokens")
    private Long totalInputTokens;

    /** 总输出 Token 消耗 */
    @JsonProperty("total_output_tokens")
    private Long totalOutputTokens;

    /** 平均延迟（毫秒） */
    @JsonProperty("avg_latency_ms")
    private Long avgLatencyMs;

    /** 最大延迟（毫秒） */
    @JsonProperty("max_latency_ms")
    private Long maxLatencyMs;

    /** 总成本估算 */
    @JsonProperty("total_cost")
    private BigDecimal totalCost;
}
