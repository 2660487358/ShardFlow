package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * 知识库状态包实体（C-4.5 通用 ContextShard 状态包）。
 * <p>
 * 规则条款：C-4.5（状态包管理）、C-6.5（版本号乐观锁）、C-3.4（三级存取）。
 * <p>
 * kb_shard 表是通用状态包的持久化存储，支持：
 * - 创建/更新状态包（带版本号乐观锁）
 * - 归档历史版本
 * - 回调聚合（Python 推理层通过回调接口写入）
 */
@Data
@NoArgsConstructor
@TableName("kb_shard")
public class KbShardEntity {

    @TableId(type = IdType.INPUT)
    private String shardId;

    /** 分片类型：session / task / knowledge / profile */
    @TableField("shard_type")
    private String shardType;

    /** 所有者用户ID */
    @TableField("owner_id")
    private String ownerId;

    /** 关联任务ID（可空） */
    @TableField("task_id")
    private String taskId;

    /** 关联会话ID（可空） */
    @TableField("session_id")
    private String sessionId;

    /** 上下文内容（JSONB） */
    @TableField("context")
    private String context;

    /** 记忆引用列表（JSONB） */
    @TableField("memory_refs")
    private String memoryRefs;

    /** 策略提示（JSONB） */
    @TableField("strategy_hints")
    private String strategyHints;

    /** 检索引用列表（JSONB） */
    @TableField("retrieved_refs")
    private String retrievedRefs;

    /** 状态：active / archived / deleted */
    @TableField("status")
    private String status;

    /** 版本号（乐观锁） */
    @TableField("version")
    private Integer version;

    @TableField("is_deleted")
    private Boolean isDeleted;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
