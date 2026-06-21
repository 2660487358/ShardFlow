package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 用户画像变更历史实体（C-9.12）。
 * <p>
 * 记录每次画像更新的增量补丁（patch）与前后快照，支持审计与回溯。
 */
@Data
@NoArgsConstructor
@TableName("user_profile_history")
public class UserProfileHistoryEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("profile_version")
    private Integer profileVersion;

    /** 变更类型：CREATE / UPDATE / DELETE */
    @TableField("change_type")
    private String changeType;

    /** JSON Patch 增量补丁（RFC 6902 格式） */
    @TableField("patch")
    private String patch;

    /** 变更前快照（JSON） */
    @TableField("before_snapshot")
    private String beforeSnapshot;

    /** 变更后快照（JSON） */
    @TableField("after_snapshot")
    private String afterSnapshot;

    /** 变更来源：callback / api / system */
    @TableField("source")
    private String source;

    /** 链路追踪ID */
    @TableField("trace_id")
    private String traceId;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
