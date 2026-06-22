package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 内容元数据实体，映射 skill_artifact 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.3 / DR-1.
 * <p>记录每个版本下 Artifact 文件（skill.json/prompt.md/tool.py/workflow.yaml/manifest.json）的元信息。
 */
@Data
@NoArgsConstructor
@TableName("skill_artifact")
public class SkillArtifactEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** 关联 skill_registry.id */
    @TableField("skill_id")
    @JsonProperty("skill_id")
    private Long skillId;

    /** 关联 skill_version.id */
    @TableField("version_id")
    @JsonProperty("version_id")
    private Long versionId;

    /** 工件类型：metadata | prompt | tool_handler | workflow_def | manifest */
    @TableField("artifact_type")
    @JsonProperty("artifact_type")
    private String artifactType;

    /** 文件名 */
    @TableField("file_name")
    @JsonProperty("file_name")
    private String fileName;

    /** 文件大小（字节） */
    @TableField("file_size")
    @JsonProperty("file_size")
    private Integer fileSize;

    /** 内容哈希（SHA-256） */
    @TableField("content_hash")
    @JsonProperty("content_hash")
    private String contentHash;

    /** MinIO 对象存储路径 */
    @TableField("minio_url")
    @JsonProperty("minio_url")
    private String minioUrl;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
