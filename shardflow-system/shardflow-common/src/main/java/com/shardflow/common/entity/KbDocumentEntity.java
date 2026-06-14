package com.shardflow.common.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.Instant;

@Data
@NoArgsConstructor
@TableName("shardflow_kb_document")
public class KbDocumentEntity {

    @TableId(type = IdType.AUTO)
    private Long id;

    @TableField("document_code")
    private String documentCode;

    @TableField("collection_id")
    private String collectionId;

    @TableField("user_id")
    private String userId;

    @TableField("filename")
    private String filename;

    @TableField("file_type")
    private String fileType;

    @TableField("file_size")
    private Long fileSize;

    @TableField("minio_url")
    private String minioUrl;

    @TableField("parse_strategy")
    private String parseStrategy;

    @TableField("status")
    private String status;

    @TableField("error_msg")
    private String errorMsg;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    private Instant createdAt;
}
