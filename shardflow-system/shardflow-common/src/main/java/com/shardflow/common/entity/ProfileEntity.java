package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_user_profile")
public class ProfileEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("user_id")
    private String userId;

    @TableField("preferences")
    private String preferences;

    @TableField("expertise")
    private String expertise;

    @TableField("habits")
    private String habits;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
