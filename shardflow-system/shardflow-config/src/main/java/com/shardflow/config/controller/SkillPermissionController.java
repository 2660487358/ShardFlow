package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.config.dto.PermissionRequest;
import com.shardflow.config.dto.SkillPermissionDTO;
import com.shardflow.config.service.SkillPermissionService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Skill 权限管理 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-8.3 / IR-7 / IR-10 / 实施计划 P6.2.
 * <p>提供 RBAC+ABAC 权限模型的配置、查询、删除接口.
 *
 * <p>权限主体类型：user | role | team | tenant
 * <p>权限位掩码：1=读 2=写 4=执行 8=管理 16=审计（位掩码可组合）
 *
 * <p>所有接口经过 Sa-Token JWT 认证（由 SaTokenConfig 全局配置 /api/v1/** 拦截），
 * 未登录请求自动返回 401（P6.2.4）。
 *
 * <p>接口清单：
 * <ul>
 *   <li>POST   /api/v1/skills/{skill_code}/permissions          — 配置权限（upsert）（P6.2.1）</li>
 *   <li>GET    /api/v1/skills/{skill_code}/permissions          — 查询权限列表（P6.2.2）</li>
 *   <li>DELETE /api/v1/skills/{skill_code}/permissions          — 撤销权限（P6.2.5）</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/skills/{skill_code}/permissions")
@RequiredArgsConstructor
public class SkillPermissionController {

    private final SkillPermissionService skillPermissionService;

    // ── P6.2.1 配置权限（upsert 语义）──

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Result<SkillPermissionDTO> configure(
            @PathVariable("skill_code") String skillCode,
            @Valid @RequestBody PermissionRequest request) {
        return Result.ok(skillPermissionService.configurePermission(skillCode, request));
    }

    // ── P6.2.2 查询权限列表 ──

    @GetMapping
    public Result<List<SkillPermissionDTO>> list(
            @PathVariable("skill_code") String skillCode) {
        return Result.ok(skillPermissionService.listPermissions(skillCode));
    }

    // ── P6.2.5 撤销权限 ──

    @DeleteMapping
    public Result<Void> revoke(
            @PathVariable("skill_code") String skillCode,
            @RequestParam("subject_type") String subjectType,
            @RequestParam("subject_id") String subjectId) {
        skillPermissionService.revokePermission(skillCode, subjectType, subjectId);
        return Result.ok();
    }
}
