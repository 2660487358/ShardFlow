package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 权限配置响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / SkillPermissionDTO.
 * <p>permission_mask 位掩码：1=读 2=写 4=执行 8=管理 16=审计。
 */
@Data
@NoArgsConstructor
public class SkillPermissionDTO {

    private Long id;

    @JsonProperty("skill_id")
    private Long skillId;

    @JsonProperty("subject_type")
    private String subjectType;

    @JsonProperty("subject_id")
    private String subjectId;

    @JsonProperty("permission_mask")
    private Integer permissionMask;

    @JsonProperty("created_at")
    private Instant createdAt;
}
