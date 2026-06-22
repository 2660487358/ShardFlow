package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 权限配置实体，映射 skill_permission 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.5 / DR-1 / DR-8.
 * <p>RBAC+ABAC 位掩码权限模型：
 * <ul>
 *   <li>主体类型 subject_type：user | role | team | tenant</li>
 *   <li>权限位掩码 permission_mask：1=读 2=写 4=执行 8=管理 16=审计</li>
 * </ul>
 */
@Data
@NoArgsConstructor
@TableName("skill_permission")
public class SkillPermissionEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** 关联 skill_registry.id */
    @TableField("skill_id")
    @JsonProperty("skill_id")
    private Long skillId;

    /** 权限主体类型：user | role | team | tenant */
    @TableField("subject_type")
    @JsonProperty("subject_type")
    private String subjectType;

    /** 权限主体ID */
    @TableField("subject_id")
    @JsonProperty("subject_id")
    private String subjectId;

    /** 位掩码：1=读 2=写 4=执行 8=管理 16=审计 */
    @TableField("permission_mask")
    @JsonProperty("permission_mask")
    private Integer permissionMask = 0;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;
}
