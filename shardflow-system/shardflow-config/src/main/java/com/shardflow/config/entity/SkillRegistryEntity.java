package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Skill 注册表实体，映射 skill_registry 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.1 / DR-1.
 * <p>JSONB 字段（trigger_keywords/input_schema/output_schema/cost_estimate/tags）以 String 存储，
 * 由业务层通过 Jackson 序列化/反序列化。
 */
@Data
@NoArgsConstructor
@TableName("skill_registry")
public class SkillRegistryEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** Skill 唯一编码，格式 SKILL-{8位UUID短码} */
    @TableField("skill_code")
    @JsonProperty("skill_code")
    private String skillCode;

    /** Skill 显示名称，最长128字符 */
    @TableField("skill_name")
    @JsonProperty("skill_name")
    private String skillName;

    @TableField("description")
    private String description;

    /** 执行模式：prompt | tool | hybrid | workflow */
    @TableField("skill_type")
    @JsonProperty("skill_type")
    private String skillType = "prompt";

    /** 信任等级：official | team | personal */
    @TableField("trust_tier")
    @JsonProperty("trust_tier")
    private String trustTier = "personal";

    /** 创建者用户ID */
    @TableField("owner_id")
    @JsonProperty("owner_id")
    private String ownerId;

    /** 所属用户标识（RLS过滤字段） */
    @TableField("user_id")
    @JsonProperty("user_id")
    private String userId;

    /** 当前生效版本号 */
    @TableField("current_version")
    @JsonProperty("current_version")
    private String currentVersion;

    /** 状态：draft | reviewing | published | deprecated | archived */
    @TableField("status")
    private String status = "draft";

    /** 触发关键词列表，JSONB格式 */
    @TableField("trigger_keywords")
    @JsonProperty("trigger_keywords")
    private String triggerKeywords;

    /** 输入参数 JSON Schema */
    @TableField("input_schema")
    @JsonProperty("input_schema")
    private String inputSchema;

    /** 输出参数 JSON Schema */
    @TableField("output_schema")
    @JsonProperty("output_schema")
    private String outputSchema;

    /** 预估成本，JSONB格式 */
    @TableField("cost_estimate")
    @JsonProperty("cost_estimate")
    private String costEstimate;

    /** Skill 运行配置，JSONB格式 */
    @TableField("config")
    private String config;

    /** 标签列表，JSONB格式 */
    @TableField("tags")
    private String tags;

    /** 技能分类 */
    @TableField("category")
    private String category = "";

    /** 来源：CUSTOM | IMPORTED | BUILTIN */
    @TableField("source")
    private String source = "CUSTOM";

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    @JsonProperty("updated_at")
    private Instant updatedAt;

    @TableField("created_by")
    @JsonProperty("created_by")
    private String createdBy;

    @TableField("updated_by")
    @JsonProperty("updated_by")
    private String updatedBy;
}
