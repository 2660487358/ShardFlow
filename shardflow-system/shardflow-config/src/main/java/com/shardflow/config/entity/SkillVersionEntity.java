package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 版本历史实体，映射 skill_version 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.2 / DR-1.
 * <p>版本不可变：已发布版本（staging/production）的 Artifact 禁止覆盖。
 * 回滚通过创建新版本记录指向旧 Artifact 实现。
 */
@Data
@NoArgsConstructor
@TableName("skill_version")
public class SkillVersionEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** 关联 skill_registry.id */
    @TableField("skill_id")
    @JsonProperty("skill_id")
    private Long skillId;

    /** 版本标签，MAJOR.MINOR.PATCH 格式 */
    @TableField("version_tag")
    @JsonProperty("version_tag")
    private String versionTag;

    /** 内容 SHA-256 哈希 */
    @TableField("content_hash")
    @JsonProperty("content_hash")
    private String contentHash;

    /** MinIO 存储路径 */
    @TableField("artifact_path")
    @JsonProperty("artifact_path")
    private String artifactPath;

    /** 变更说明（发布时必填） */
    @TableField("change_log")
    @JsonProperty("change_log")
    private String changeLog;

    /** 发布者ID */
    @TableField("promoted_by")
    @JsonProperty("promoted_by")
    private String promotedBy;

    /** 发布时间 */
    @TableField("promoted_at")
    @JsonProperty("promoted_at")
    private Instant promotedAt;

    /** 版本状态：draft | staging | production | rolled_back */
    @TableField("status")
    private String status = "draft";

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
