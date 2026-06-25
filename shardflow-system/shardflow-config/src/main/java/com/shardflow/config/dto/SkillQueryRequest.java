package com.shardflow.config.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Skill 列表查询参数 DTO.
 *
 * <p>Per Skills管理需求规格文档 FR-4 / 实施计划 P2.2.2 / P2.3.
 * <p>支持分页 + 关键词搜索 + 状态筛选。
 * <p>分类/信任等级/执行模式筛选已移除（端到端改造）。
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

    /** 状态筛选: draft|reviewing|published|deprecated|archived（FR-4.3） */
    private String status;
}
