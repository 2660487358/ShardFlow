package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_user")
public class UserEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("username")
    private String username;

    @TableField("password_hash")
    private String passwordHash;

    @TableField("user_id")
    private String userId;

    @TableField("role")
    private String role = "USER";

    @TableField("enabled")
    private boolean enabled = true;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
