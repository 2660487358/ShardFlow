package com.shardflow.config.service;

import com.shardflow.config.dto.ImportResult;
import org.springframework.web.multipart.MultipartFile;

/**
 * Skill 导入服务接口.
 *
 * <p>Per Skills管理需求规格文档 FR-3 / 实施计划 P3.3.
 */
public interface SkillImportService {

    /**
     * 从 JSON 文件导入 Skill.
     * FR-3.1 / P3.3.1: POST /api/v1/skills/import
     *
     * @param file JSON 文件
     * @return 导入结果统计
     */
    ImportResult importSkills(MultipartFile file);
}
