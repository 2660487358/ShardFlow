package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Map;

/**
 * Skill 审计日志响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / SkillAuditLogDTO.
 */
@Data
@NoArgsConstructor
public class SkillAuditLogDTO {

    private Long id;

    @JsonProperty("skill_id")
    private Long skillId;

    @JsonProperty("agent_id")
    private String agentId;

    private String operation;

    @JsonProperty("operator_id")
    private String operatorId;

    @JsonProperty("operator_type")
    private String operatorType;

    @JsonProperty("request_id")
    private String requestId;

    private Map<String, Object> details;

    @JsonProperty("ip_address")
    private String ipAddress;

    @JsonProperty("user_agent")
    private String userAgent;

    @JsonProperty("created_at")
    private Instant createdAt;
}
