package com.shardflow.config.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Skill 状态切换请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-1 / FR-1.6.
 * <p>状态流转（DR-2）：draft ↔ reviewing ↔ published ↔ deprecated → archived。
 */
@Data
@NoArgsConstructor
public class SkillStatusRequest {

    @NotBlank(message = "状态不能为空")
    @Pattern(regexp = "draft|reviewing|published|deprecated|archived",
             message = "status 必须为 draft/reviewing/published/deprecated/archived")
    private String status;
}
