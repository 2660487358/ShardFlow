package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.config.dto.*;
import com.shardflow.config.service.AgentSkillBindingService;
import com.shardflow.config.service.SkillExportService;
import com.shardflow.config.service.SkillImportService;
import com.shardflow.config.service.SkillService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Skill 生命周期管理 REST API.
 *
 * <p>Per Skills管理需求规格文档 FR-1 / FR-4 / 实施计划 P2.2~P2.4.
 * <p>提供 Skill 的 CRUD、状态切换、分类搜索接口。
 * <p>所有接口经过 Sa-Token JWT 认证（由 SaTokenConfig 全局配置 /api/v1/** 拦截）。
 * <p>用户隔离通过 UserContext.getUserId() 自动注入。
 *
 * <p>接口清单：
 * <ul>
 *   <li>POST   /api/v1/skills              — 创建 Skill（P2.2.1）</li>
 *   <li>GET    /api/v1/skills              — 列表查询（P2.2.2）</li>
 *   <li>GET    /api/v1/skills/{skill_code} — 详情查询（P2.2.3）</li>
 *   <li>PUT    /api/v1/skills/{skill_code} — 更新 Skill（P2.2.4）</li>
 *   <li>DELETE /api/v1/skills/{skill_code} — 删除 Skill（P2.2.5）</li>
 *   <li>PATCH  /api/v1/skills/{skill_code}/status — 状态切换（P2.2.6）</li>
 *   <li>GET    /api/v1/skills/{skill_code}/agents — 关联 Agent 查询（P4.1.5）</li>
 * </ul>
 */
@RestController
@RequestMapping("/api/v1/skills")
@RequiredArgsConstructor
public class SkillController {

    private final SkillService skillService;
    private final SkillImportService skillImportService;
    private final SkillExportService skillExportService;
    private final AgentSkillBindingService bindingService;

    // ── P2.2.1 创建 Skill ──

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Result<SkillDTO> create(@Valid @RequestBody CreateSkillRequest request) {
        return Result.ok(skillService.createSkill(request));
    }

    // ── P2.2.2 列表查询（分页+多条件筛选）──

    @GetMapping
    public Result<Map<String, Object>> list(@Valid SkillQueryRequest query) {
        return Result.ok(skillService.listSkills(query));
    }

    // ── P2.2.3 详情查询 ──

    @GetMapping("/{skill_code}")
    public Result<SkillDetailDTO> detail(@PathVariable("skill_code") String skillCode) {
        return Result.ok(skillService.getSkillDetail(skillCode));
    }

    // ── P2.2.4 更新 Skill ──

    @PutMapping("/{skill_code}")
    public Result<SkillDTO> update(
            @PathVariable("skill_code") String skillCode,
            @Valid @RequestBody UpdateSkillRequest request) {
        return Result.ok(skillService.updateSkill(skillCode, request));
    }

    // ── P2.2.5 删除 Skill（级联删除）──

    @DeleteMapping("/{skill_code}")
    public Result<Void> delete(@PathVariable("skill_code") String skillCode) {
        skillService.deleteSkill(skillCode);
        return Result.ok();
    }

    // ── P2.2.6 状态切换 ──

    @PatchMapping("/{skill_code}/status")
    public Result<SkillDTO> changeStatus(
            @PathVariable("skill_code") String skillCode,
            @Valid @RequestBody SkillStatusRequest request) {
        return Result.ok(skillService.changeStatus(skillCode, request));
    }

    // ── P3.3.1 Skill 导入 ──

    @PostMapping("/import")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<ImportResult> importSkills(@RequestParam("file") MultipartFile file) {
        return Result.ok(skillImportService.importSkills(file));
    }

    // ── P4.1.5 Skill 关联 Agent 查询 ──

    @GetMapping("/{skill_code}/agents")
    public Result<List<SkillDetailDTO.AgentRef>> getSkillAgents(
            @PathVariable("skill_code") String skillCode) {
        return Result.ok(bindingService.listSkillAgents(skillCode));
    }

    // ── P3.4.1 Skill 导出 ──

    @GetMapping("/export")
    public ResponseEntity<byte[]> exportSkills(@RequestParam("ids") String ids) {
        List<Long> idList = Arrays.stream(ids.split(","))
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(Long::parseLong)
            .collect(Collectors.toList());

        String json = skillExportService.exportSkills(idList);
        byte[] body = json.getBytes(StandardCharsets.UTF_8);

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setContentDispositionFormData("attachment", "skills-export.json");

        return new ResponseEntity<>(body, headers, HttpStatus.OK);
    }
}
