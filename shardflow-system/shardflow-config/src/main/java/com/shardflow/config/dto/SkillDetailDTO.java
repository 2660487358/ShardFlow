package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * Skill 详情响应 DTO，含关联 Agent 列表和版本历史.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / SkillDetailDTO.
 */
@Data
@NoArgsConstructor
@EqualsAndHashCode(callSuper = true)
public class SkillDetailDTO extends SkillDTO {

    /** 关联 Agent 列表 */
    private List<AgentRef> agents;

    /** 版本历史 */
    private List<VersionRef> versions;

    /** 关联 Agent 摘要信息 */
    @Data
    @NoArgsConstructor
    public static class AgentRef {
        private Long id;
        private String name;

        @JsonProperty("agent_code")
        private String agentCode;

        @JsonProperty("binding_type")
        private String bindingType;

        private Integer priority;
    }

    /** 版本摘要信息 */
    @Data
    @NoArgsConstructor
    public static class VersionRef {
        @JsonProperty("version_tag")
        private String versionTag;

        private String status;

        @JsonProperty("change_log")
        private String changeLog;

        @JsonProperty("promoted_by")
        private String promotedBy;

        @JsonProperty("promoted_at")
        private java.time.Instant promotedAt;
    }
}
