package com.shardflow.config.entity;

import com.baomidou.mybatisplus.annotation.*;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Agent-Skill 绑定关系实体，映射 agent_skill_binding 表.
 *
 * <p>Per Skills管理需求规格文档 7.1.4 / DR-1.
 * <p>通过独立关联表管理 Agent-Skill 关系，不修改 shardflow_agent_config 表结构（D-3）。
 * agent_id 关联 shardflow_agent_config.agent_code。
 */
@Data
@NoArgsConstructor
@TableName("agent_skill_binding")
public class AgentSkillBindingEntity {

    @TableId(type = IdType.AUTO)
    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private Long id;

    /** Agent 编码（关联 shardflow_agent_config.agent_code） */
    @TableField("agent_id")
    @JsonProperty("agent_id")
    private String agentId;

    /** 关联 skill_registry.id */
    @TableField("skill_id")
    @JsonProperty("skill_id")
    private Long skillId;

    /** 绑定的 Skill 版本号 */
    @TableField("bound_version")
    @JsonProperty("bound_version")
    private String boundVersion;

    /** 绑定类型：required | optional */
    @TableField("binding_type")
    @JsonProperty("binding_type")
    private String bindingType = "optional";

    /** 优先级，数值越大优先级越高 */
    @TableField("priority")
    private Integer priority = 0;

    /** Agent 级别的配置覆盖，JSONB格式 */
    @TableField("config_override")
    @JsonProperty("config_override")
    private String configOverride;

    /** 是否启用：1=启用 0=禁用 */
    @TableField("enabled")
    private Integer enabled = 1;

    @TableField(value = "created_at", fill = FieldFill.INSERT)
    @JsonProperty("created_at")
    private Instant createdAt;

    @TableField(value = "updated_at", fill = FieldFill.INSERT_UPDATE)
    @JsonProperty("updated_at")
    private Instant updatedAt;

    @TableField("created_by")
    @JsonProperty("created_by")
    private String createdBy;
}
