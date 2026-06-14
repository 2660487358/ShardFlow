package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("user_profiles")
public class UserProfileEntity {

    @TableId(type = IdType.AUTO)
    private Long profileId;

    @TableField("user_id")
    private String userId;

    @TableField("profile_version")
    private Integer profileVersion;

    @TableField("preference")
    private String preference;

    @TableField("interaction_habits")
    private String interactionHabits;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;

    @TableField("deleted_at")
    private Instant deletedAt;
}
