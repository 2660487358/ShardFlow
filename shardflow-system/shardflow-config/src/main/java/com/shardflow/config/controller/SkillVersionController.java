package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.config.dto.PublishVersionRequest;
import com.shardflow.config.dto.SkillArtifactDTO;
import com.shardflow.config.dto.SkillVersionDTO;
import com.shardflow.config.service.SkillVersionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;

/**
 * Skill 版本管理 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-2 / FR-6 / 实施计划 P3.1 / P3.2.
 * <p>提供 Skill 版本发布、回滚、历史查询、Artifact 上传接口。
 *
 * <p>接口清单：
 * <ul>
 *   <li>POST /api/v1/skills/{skill_code}/versions/{version_tag}/publish  — 发布版本（P3.1.1）</li>
 *   <li>GET  /api/v1/skills/{skill_code}/versions                      — 版本历史（P3.1.3）</li>
 *   <li>POST /api/v1/skills/{skill_code}/versions/{version_tag}/rollback — 版本回滚（P3.1.4）</li>
 *   <li>POST /api/v1/skills/{skill_code}/versions/{version_tag}/artifacts — Artifact 上传（P3.2.1）</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/skills/{skill_code}/versions")
@RequiredArgsConstructor
public class SkillVersionController {

    private final SkillVersionService skillVersionService;

    // ── P3.1.1 发布版本 ──

    @PostMapping("/{version_tag}/publish")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<SkillVersionDTO> publishVersion(
            @PathVariable("skill_code") String skillCode,
            @PathVariable("version_tag") String versionTag,
            @Valid @RequestBody PublishVersionRequest request) {
        return Result.ok(skillVersionService.publishVersion(skillCode, versionTag, request));
    }

    // ── P3.1.3 版本历史查询 ──

    @GetMapping
    public Result<List<SkillVersionDTO>> listVersions(
            @PathVariable("skill_code") String skillCode) {
        return Result.ok(skillVersionService.listVersions(skillCode));
    }

    // ── P3.1.4 版本回滚 ──

    @PostMapping("/{version_tag}/rollback")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<SkillVersionDTO> rollbackVersion(
            @PathVariable("skill_code") String skillCode,
            @PathVariable("version_tag") String versionTag) {
        return Result.ok(skillVersionService.rollbackVersion(skillCode, versionTag));
    }

    // ── P3.2.1 Artifact 上传 ──

    @PostMapping("/{version_tag}/artifacts")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<SkillArtifactDTO> uploadArtifact(
            @PathVariable("skill_code") String skillCode,
            @PathVariable("version_tag") String versionTag,
            @RequestParam("file") MultipartFile file) {
        return Result.ok(skillVersionService.uploadArtifact(skillCode, versionTag, file));
    }
}
