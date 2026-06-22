package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Skill 权限配置请求 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-7 / FR-8.3.
 * <p>RBAC+ABAC 位掩码权限模型：
 * <ul>
 *   <li>subject_type：user | role | team | tenant</li>
 *   <li>permission_mask：1=读 2=写 4=执行 8=管理 16=审计（位掩码可组合）</li>
 * </ul>
 */
@Data
@NoArgsConstructor
public class PermissionRequest {

    @NotBlank(message = "权限主体类型不能为空")
    @Pattern(regexp = "user|role|team|tenant",
             message = "subject_type 必须为 user/role/team/tenant")
    @JsonProperty("subject_type")
    private String subjectType;

    @NotBlank(message = "权限主体ID不能为空")
    @JsonProperty("subject_id")
    private String subjectId;

    @NotNull(message = "权限位掩码不能为空")
    @Min(value = 0, message = "权限位掩码不能为负数")
    @JsonProperty("permission_mask")
    private Integer permissionMask;
}
