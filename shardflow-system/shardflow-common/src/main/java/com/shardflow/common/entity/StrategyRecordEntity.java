package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("strategy_records")
public class StrategyRecordEntity {

    @TableId(type = IdType.INPUT)
    private String recordId;

    @TableField("user_id")
    private String userId;

    @TableField("task_type")
    private String taskType;

    @TableField("query_pattern")
    private String queryPattern;

    @TableField("tool_combo")
    private String toolCombo;

    @TableField("user_feedback")
    private String userFeedback;

    @TableField("success_score")
    private BigDecimal successScore;

    @TableField("cost_ms")
    private Integer costMs;

    @TableField("is_deleted")
    private Boolean isDeleted;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
