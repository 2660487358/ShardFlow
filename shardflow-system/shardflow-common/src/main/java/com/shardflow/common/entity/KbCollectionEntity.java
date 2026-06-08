package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_kb_collection")
public class KbCollectionEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("collection_code")
    private String collectionCode;

    @TableField("user_id")
    private String userId;

    @TableField("name")
    private String name;

    @TableField("description")
    private String description;

    @TableField("icon")
    private String icon;

    @TableField("status")
    private String status;

    @TableField("doc_count")
    private Integer docCount;

    @TableField("chunk_count")
    private Integer chunkCount;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    private Instant updatedAt;
}
