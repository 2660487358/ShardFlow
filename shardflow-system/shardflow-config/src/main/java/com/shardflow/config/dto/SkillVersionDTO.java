package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 版本历史响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / SkillVersionDTO.
 */
@Data
@NoArgsConstructor
public class SkillVersionDTO {

    private Long id;

    @JsonProperty("skill_id")
    private Long skillId;

    @JsonProperty("version_tag")
    private String versionTag;

    @JsonProperty("content_hash")
    private String contentHash;

    @JsonProperty("artifact_path")
    private String artifactPath;

    @JsonProperty("change_log")
    private String changeLog;

    @JsonProperty("promoted_by")
    private String promotedBy;

    @JsonProperty("promoted_at")
    private Instant promotedAt;

    private String status;

    @JsonProperty("created_at")
    private Instant createdAt;
}
