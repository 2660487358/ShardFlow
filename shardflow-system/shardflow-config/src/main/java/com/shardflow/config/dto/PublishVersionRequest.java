package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Skill 版本发布请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-2 / FR-2.1 / FR-2.6.
 * <p>POST /api/v1/skills/{skill_code}/versions/{version_tag}/publish
 */
@Data
@NoArgsConstructor
public class PublishVersionRequest {

    @NotBlank(message = "变更说明不能为空")
    @Size(max = 2000, message = "变更说明最长2000字符")
    @JsonProperty("change_log")
    private String changeLog;

    /**
     * 提升类型：staging（默认）或 production.
     * <p>staging 为预发布状态，production 为生产生效状态。
     */
    @Pattern(regexp = "staging|production",
             message = "promotion_type 必须为 staging/production")
    @JsonProperty("promotion_type")
    private String promotionType = "staging";
}
