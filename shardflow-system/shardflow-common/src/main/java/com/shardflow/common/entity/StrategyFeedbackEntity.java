package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_strategy_feedback")
public class StrategyFeedbackEntity {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    @TableField("strategy_code")
    private String strategyCode;

    @TableField("user_id")
    private String userId;

    @TableField("feedback_type")
    private String feedbackType;

    @TableField("comment")
    private String comment;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
