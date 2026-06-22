package com.shardflow.config.service;

import com.shardflow.config.dto.PublishVersionRequest;
import com.shardflow.config.dto.SkillArtifactDTO;
import com.shardflow.config.dto.SkillVersionDTO;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Skill 版本管理服务接口.
 *
 * <p>Per Skills管理需求规格文档 FR-2 / FR-6 / 实施计划 P3.1 / P3.2.
 * <p>提供 Skill 版本发布、回滚、历史查询、Artifact 上传。
 */
public interface SkillVersionService {

    /**
     * 发布 Skill 版本.
     * FR-2.1 / P3.1.1: POST /api/v1/skills/{skill_code}/versions/{version_tag}/publish
     *
     * @param skillCode Skill 编码
     * @param versionTag 版本标签
     * @param request 发布请求
     * @return 版本 DTO
     */
    SkillVersionDTO publishVersion(String skillCode, String versionTag, PublishVersionRequest request);

    /**
     * 查询 Skill 版本历史.
     * FR-2.3 / P3.1.3: GET /api/v1/skills/{skill_code}/versions
     *
     * @param skillCode Skill 编码
     * @return 版本列表
     */
    List<SkillVersionDTO> listVersions(String skillCode);

    /**
     * 回滚 Skill 到指定版本.
     * FR-2.4 / P3.1.4: POST /api/v1/skills/{skill_code}/versions/{version_tag}/rollback
     *
     * @param skillCode Skill 编码
     * @param versionTag 目标版本标签
     * @return 新版本 DTO
     */
    SkillVersionDTO rollbackVersion(String skillCode, String versionTag);

    /**
     * 上传 Skill Artifact.
     * FR-6.8 / P3.2.1: POST /api/v1/skills/{skill_code}/versions/{version_tag}/artifacts
     *
     * @param skillCode Skill 编码
     * @param versionTag 版本标签
     * @param file 上传文件
     * @return Artifact 元数据 DTO
     */
    SkillArtifactDTO uploadArtifact(String skillCode, String versionTag, MultipartFile file);
}
