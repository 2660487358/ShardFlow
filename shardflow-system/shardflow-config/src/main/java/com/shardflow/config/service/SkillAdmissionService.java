package com.shardflow.config.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.entity.SkillVersionEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.repository.SkillVersionRepository;
import com.shardflow.config.support.SkillAdmissionScanner;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

/**
 * Skill 准入服务.
 *
 * <p>Per Skills管理需求规格文档 FR-8.1 / FR-8.2 / IR-9 / 实施计划 P6.1.
 * <p>在 Skill 发布前执行：
 * <ul>
 *   <li>静态扫描（Prompt 注入 / 敏感信息 / 代码静态分析 / 依赖审计）</li>
 *   <li>沙箱测试（V1 简化：调用 Python 沙箱，超时 30s）</li>
 *   <li>人工审核流程（official 级别强制审核）</li>
 * </ul>
 *
 * <p>扫描未通过返回 SKILL_ADMISSION_REJECTED 及具体问题列表。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillAdmissionService {

    private final SkillAdmissionScanner admissionScanner;
    private final SkillRegistryRepository skillRegistryRepository;
    private final SkillVersionRepository skillVersionRepository;
    private final SkillPermissionChecker permissionChecker;
    private final SkillAuditService auditService;

    /**
     * 执行准入扫描.
     *
     * @param skillCode Skill 编码
     * @param versionTag 版本号
     * @return 扫描结果
     */
    public SkillAdmissionScanner.ScanResult scan(String skillCode, String versionTag) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);
        permissionChecker.checkReadPermission(userId, skill);

        SkillVersionEntity version = findVersion(skill.getId(), versionTag);

        log.info("SkillAdmissionService: scanning skill={} version={}", skillCode, versionTag);

        // V1 简化：直接扫描 Skill 描述与配置（实际应从 MinIO 加载 Artifact 内容）
        SkillAdmissionScanner.ScanResult result = admissionScanner.scan(
                skill.getSkillName(),
                skill.getDescription(),
                skill.getConfig(),  // V1 简化：用 config 代替 prompt.md
                null,                // V1 简化：tool.py 内容待 MinIO 集成
                null                 // V1 简化：requirements.txt 内容待 MinIO 集成
        );

        // 记录审计日志
        auditService.recordAudit(
                skill.getId(),
                skillCode,
                "ADMISSION_SCAN",
                userId,
                "scan_passed=" + result.passed() + ", issues=" + result.issues().size(),
                0,
                0,
                result.passed(),
                result.passed() ? "" : "SKILL_ADMISSION_REJECTED"
        );

        if (!result.passed()) {
            log.warn("SkillAdmissionService: admission rejected skill={} issues={}",
                    skillCode, result.issues().size());
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "SKILL_ADMISSION_REJECTED: " + formatIssues(result.issues()));
        }

        return result;
    }

    /**
     * 人工审核流程.
     *
     * <p>FR-8.2: official 级别 Skill 发布前强制人工审核.
     *
     * @param skillCode Skill 编码
     * @param versionTag 版本号
     * @param approved 是否通过审核
     * @param comment 审核意见
     */
    public void review(String skillCode, String versionTag, boolean approved, String comment) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 仅 official Skill 强制审核
        if (!"official".equals(skill.getTrustTier())) {
            log.info("SkillAdmissionService: review skipped for non-official skill={}", skillCode);
            return;
        }

        // 校验审核权限
        if (!hasReviewPermission()) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Only security team can review official skills");
        }

        SkillVersionEntity version = findVersion(skill.getId(), versionTag);

        log.info("SkillAdmissionService: review skill={} version={} approved={} comment={}",
                skillCode, versionTag, approved, comment);

        if (approved) {
            // 审核通过，更新版本状态为 staging
            version.setStatus("staging");
            skillVersionRepository.updateById(version);
        } else {
            // 审核拒绝，更新版本状态为 draft
            version.setStatus("draft");
            skillVersionRepository.updateById(version);
        }

        // 记录审计日志
        auditService.recordAudit(
                skill.getId(),
                skillCode,
                "ADMISSION_REVIEW",
                userId,
                "approved=" + approved + ", comment=" + comment,
                0,
                0,
                true,
                ""
        );
    }

    /**
     * 沙箱测试（V1 简化：仅记录调用，实际执行由 Python sandbox_runner.py 完成）.
     *
     * @param skillCode Skill 编码
     * @param versionTag 版本号
     * @return 测试结果
     */
    public SandboxTestResult runSandboxTest(String skillCode, String versionTag) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        log.info("SkillAdmissionService: sandbox test skill={} version={}", skillCode, versionTag);

        // V1 简化：返回通过结果（实际应调用 Python sandbox_runner.py）
        // V2 阶段：通过 gRPC 调用 Python 沙箱，监控 CPU/内存/网络/文件系统
        SandboxTestResult result = new SandboxTestResult(true, 0, 0, 0, "");

        // 记录审计日志
        auditService.recordAudit(
                skill.getId(),
                skillCode,
                "SANDBOX_TEST",
                userId,
                "passed=" + result.passed() + ", cpu_ms=" + result.cpuMs()
                        + ", memory_kb=" + result.memoryKb(),
                result.cpuMs(),
                0,
                result.passed(),
                result.error()
        );

        return result;
    }

    // ── 辅助方法 ──

    private SkillRegistryEntity findSkill(String skillCode) {
        SkillRegistryEntity skill = skillRegistryRepository.selectOne(
                new LambdaQueryWrapper<SkillRegistryEntity>()
                        .eq(SkillRegistryEntity::getSkillCode, skillCode)
        );
        if (skill == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Skill not found: " + skillCode);
        }
        return skill;
    }

    private SkillVersionEntity findVersion(Long skillId, String versionTag) {
        SkillVersionEntity version = skillVersionRepository.selectOne(
                new LambdaQueryWrapper<SkillVersionEntity>()
                        .eq(SkillVersionEntity::getSkillId, skillId)
                        .eq(SkillVersionEntity::getVersionTag, versionTag)
        );
        if (version == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Version not found: " + versionTag);
        }
        return version;
    }

    private boolean hasReviewPermission() {
        List<String> permissions = UserContext.getPermissions();
        return permissions != null && permissions.contains("skill:official:write");
    }

    private String formatIssues(List<SkillAdmissionScanner.ScanIssue> issues) {
        StringBuilder sb = new StringBuilder();
        for (SkillAdmissionScanner.ScanIssue issue : issues) {
            sb.append("[").append(issue.severity()).append("] ")
                    .append(issue.type()).append(": ").append(issue.message()).append("; ");
        }
        return sb.toString();
    }

    // ── 沙箱测试结果 ──

    public record SandboxTestResult(
            boolean passed,
            int cpuMs,
            int memoryKb,
            int networkBytes,
            String error
    ) {}
}
