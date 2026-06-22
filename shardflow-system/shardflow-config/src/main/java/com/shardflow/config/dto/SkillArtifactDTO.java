package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill Artifact 元数据响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / FR-6.
 */
@Data
@NoArgsConstructor
public class SkillArtifactDTO {

    private Long id;

    @JsonProperty("skill_id")
    private Long skillId;

    @JsonProperty("version_id")
    private Long versionId;

    @JsonProperty("artifact_type")
    private String artifactType;

    @JsonProperty("file_name")
    private String fileName;

    @JsonProperty("file_size")
    private Integer fileSize;

    @JsonProperty("content_hash")
    private String contentHash;

    @JsonProperty("minio_url")
    private String minioUrl;

    @JsonProperty("created_at")
    private Instant createdAt;
}
