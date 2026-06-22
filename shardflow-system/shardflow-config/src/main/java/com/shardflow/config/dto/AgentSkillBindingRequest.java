package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Agent-Skill 绑定批量更新请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 FR-5.5 / 实施计划 P4.1.
 * <p>请求体接收完整 bindings 数组，服务端采用全量替换语义：先删除 Agent 现有绑定，再插入新绑定。
 */
@Data
@NoArgsConstructor
public class AgentSkillBindingRequest {

    /** 绑定列表 */
    @NotNull(message = "bindings 不能为空")
    private List<BindingItem> bindings;

    /** 单个绑定项 */
    @Data
    @NoArgsConstructor
    public static class BindingItem {

        @NotNull(message = "skill_id 不能为空")
        @JsonProperty("skill_id")
        private Long skillId;

        /** 绑定版本号，空字符串表示使用 Skill 当前版本 */
        @JsonProperty("bound_version")
        private String boundVersion;

        @Pattern(regexp = "required|optional", message = "binding_type 必须为 required/optional")
        @JsonProperty("binding_type")
        private String bindingType = "optional";

        /** 优先级，数值越大优先级越高 */
        private Integer priority = 0;

        /** Agent 级别配置覆盖，JSON 对象 */
        @JsonProperty("config_override")
        private Map<String, Object> configOverride;

        /** 是否启用：1=启用 0=禁用 */
        private Integer enabled = 1;
    }
}