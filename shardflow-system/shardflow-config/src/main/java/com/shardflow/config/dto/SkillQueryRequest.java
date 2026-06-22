package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Skill 列表查询参数 DTO.
 *
 * <p>Per Skills管理需求规格文档 FR-4 / 实施计划 P2.2.2 / P2.3.
 * <p>支持分页 + 多条件组合筛选（关键词/分类/状态/信任等级/执行模式）。
 */
@Data
@NoArgsConstructor
public class SkillQueryRequest {

    /** 页码，默认1 */
    @Min(value = 1, message = "页码最小为1")
    private Integer page = 1;

    /** 每页条数，默认20，最大100 */
    @Min(value = 1, message = "每页条数最小为1")
    @Max(value = 100, message = "每页条数最大为100")
    private Integer size = 20;

    /** 关键词搜索（skill_name + description 模糊匹配，FR-4.1） */
    private String keyword;

    /** 分类筛选（FR-4.2） */
    private String category;

    /** 状态筛选: draft|reviewing|published|deprecated|archived（FR-4.3） */
    private String status;

    /** 信任等级筛选: official|team|personal（FR-4.4） */
    @JsonProperty("trust_tier")
    private String trustTier;

    /** 执行模式筛选: prompt|tool|hybrid|workflow（FR-4.5） */
    @JsonProperty("skill_type")
    private String skillType;
}
