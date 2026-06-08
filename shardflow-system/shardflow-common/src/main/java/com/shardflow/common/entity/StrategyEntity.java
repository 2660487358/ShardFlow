package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_strategy")
public class StrategyEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("strategy_code")
    private String strategyCode;

    @TableField("user_id")
    private String userId;

    @TableField("task_type")
    private String taskType;

    @TableField("query_pattern")
    private String queryPattern;

    @TableField("source_combo")
    private String sourceCombo;

    @TableField("success_score")
    private double successScore;

    @TableField("cost_ms")
    private int costMs;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
