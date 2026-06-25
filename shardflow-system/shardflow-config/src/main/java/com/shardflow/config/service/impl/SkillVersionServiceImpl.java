package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.dto.PublishVersionRequest;
import com.shardflow.config.dto.SkillArtifactDTO;
import com.shardflow.config.dto.SkillVersionDTO;
import com.shardflow.config.entity.SkillArtifactEntity;
import com.shardflow.config.entity.SkillAuditLogEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.entity.SkillVersionEntity;
import com.shardflow.config.repository.SkillArtifactRepository;
import com.shardflow.config.repository.SkillAuditLogRepository;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.repository.SkillVersionRepository;
import com.shardflow.config.service.SkillArtifactStorageService;
import com.shardflow.config.service.SkillCacheEvictor;
import com.shardflow.config.service.SkillVersionService;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.config.support.SkillVersionStateMachine;
import com.shardflow.usercontext.context.UserContext;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Skill 版本管理服务实现.
 *
 * <p>Per Skills管理需求规格文档 FR-2 / FR-6 / 实施计划 P3.1 / P3.2.
 * <p>实现版本发布、回滚、历史查询、Artifact 上传与不可变性校验。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillVersionServiceImpl implements SkillVersionService {

    private static final Pattern VERSION_TAG_PATTERN = Pattern.compile(
        "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$");

    private static final long MAX_ARTIFACT_SIZE_BYTES = 10 * 1024 * 1024L; // 10MB

    private final SkillRegistryRepository skillRegistryRepo;
    private final SkillVersionRepository skillVersionRepo;
    private final SkillArtifactRepository skillArtifactRepo;
    private final SkillAuditLogRepository skillAuditLogRepo;
    private final SkillArtifactStorageService artifactStorageService;
    private final SkillCacheEvictor cacheEvictor;
    private final SkillPermissionChecker permissionChecker;
    private final ObjectMapper objectMapper;

    // ======================== P3.1.1 版本发布 ========================

    @Override
    @Transactional
    public SkillVersionDTO publishVersion(String skillCode, String versionTag, PublishVersionRequest request) {
        String userId = UserContext.getUserId();

        // P3.1.2: 版本号格式校验
        validateVersionTag(versionTag);

        // P3.1.8: 变更说明必填（@NotBlank 已校验，这里兜底）
        if (request.getChangeLog() == null || request.getChangeLog().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "change_log is required");
        }

        SkillRegistryEntity skill = findSkillByCode(skillCode, userId);
        permissionChecker.checkWritePermission(userId, skill);

        // 查找或创建版本记录
        SkillVersionEntity version = skillVersionRepo.selectOne(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skill.getId())
                .eq(SkillVersionEntity::getVersionTag, versionTag)
        );

        if (version == null) {
            version = new SkillVersionEntity();
            version.setSkillId(skill.getId());
            version.setVersionTag(versionTag);
            version.setStatus("draft");
            version.setChangeLog(request.getChangeLog());
            skillVersionRepo.insert(version);
        }

        String targetStatus = request.getPromotionType() != null
            ? request.getPromotionType()
            : "staging";

        // P3.1.5: 版本状态流转校验（draft → staging/production）
        String currentStatus = version.getStatus() != null ? version.getStatus() : "draft";
        SkillVersionStateMachine.checkTransition(currentStatus, targetStatus);

        // 查询该版本下所有 Artifact
        List<SkillArtifactEntity> artifacts = skillArtifactRepo.selectList(
            new LambdaQueryWrapper<SkillArtifactEntity>()
                .eq(SkillArtifactEntity::getSkillId, skill.getId())
                .eq(SkillArtifactEntity::getVersionId, version.getId())
        );

        if (artifacts.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "No artifacts found for version: " + versionTag);
        }

        // P3.1.6: 计算 Artifact 内容哈希 SHA-256
        String contentHash = computeVersionContentHash(artifacts);

        // 更新版本记录
        version.setContentHash(contentHash);
        version.setArtifactPath(buildArtifactPath(userId, skillCode, versionTag));
        version.setChangeLog(request.getChangeLog());
        version.setPromotedBy(userId);
        version.setPromotedAt(Instant.now());
        version.setStatus(targetStatus);
        skillVersionRepo.updateById(version);

        // 如果发布到 production，将当前其他 production 版本标记为 rolled_back，并更新 current_version
        if ("production".equals(targetStatus)) {
            markOtherProductionAsRolledBack(skill.getId(), version.getId());
            skill.setCurrentVersion(versionTag);
            skill.setUpdatedBy(userId);
            skillRegistryRepo.updateById(skill);
        }

        recordAuditLog(skill.getId(), "VERSION_PUBLISH",
            Map.of("action", "version_publish", "version", versionTag, "target_status", targetStatus));

        cacheEvictor.evictOnVersionPublish(userId, skillCode);

        log.info("Published skill version: skillCode={}, version={}, targetStatus={}, userId={}",
            skillCode, versionTag, targetStatus, userId);
        return toVersionDTO(version);
    }

    // ======================== P3.1.3 版本历史查询 ========================

    @Override
    public List<SkillVersionDTO> listVersions(String skillCode) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkillByCode(skillCode, userId);
        permissionChecker.checkReadPermission(userId, skill);

        List<SkillVersionEntity> versions = skillVersionRepo.selectList(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skill.getId())
                .orderByDesc(SkillVersionEntity::getCreatedAt)
        );

        return versions.stream()
            .map(this::toVersionDTO)
            .collect(Collectors.toList());
    }

    // ======================== P3.1.4 版本回滚 ========================

    @Override
    @Transactional
    public SkillVersionDTO rollbackVersion(String skillCode, String versionTag) {
        String userId = UserContext.getUserId();

        validateVersionTag(versionTag);

        SkillRegistryEntity skill = findSkillByCode(skillCode, userId);
        permissionChecker.checkWritePermission(userId, skill);

        SkillVersionEntity targetVersion = skillVersionRepo.selectOne(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skill.getId())
                .eq(SkillVersionEntity::getVersionTag, versionTag)
        );

        if (targetVersion == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                "Version not found: " + versionTag);
        }

        if (!"staging".equals(targetVersion.getStatus()) && !"production".equals(targetVersion.getStatus())) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Can only rollback staging or production version: " + versionTag);
        }

        // 生成新版本号：基于目标版本 PATCH + 1
        String newVersionTag = generateNextPatchVersion(skill.getId(), versionTag);

        // 创建新版本记录，指向旧 Artifact
        SkillVersionEntity newVersion = new SkillVersionEntity();
        newVersion.setSkillId(skill.getId());
        newVersion.setVersionTag(newVersionTag);
        newVersion.setContentHash(targetVersion.getContentHash());
        newVersion.setArtifactPath(targetVersion.getArtifactPath());
        newVersion.setChangeLog("Rollback to version " + versionTag);
        newVersion.setPromotedBy(userId);
        newVersion.setPromotedAt(Instant.now());
        newVersion.setStatus("production");
        skillVersionRepo.insert(newVersion);

        // 将当前 production 版本标记为 rolled_back
        markOtherProductionAsRolledBack(skill.getId(), newVersion.getId());

        // 更新 Skill 当前版本
        skill.setCurrentVersion(newVersionTag);
        skill.setUpdatedBy(userId);
        skillRegistryRepo.updateById(skill);

        recordAuditLog(skill.getId(), "VERSION_ROLLBACK",
            Map.of("action", "version_rollback", "from_version", versionTag, "new_version", newVersionTag));

        cacheEvictor.evictOnVersionPublish(userId, skillCode);

        log.info("Rolled back skill version: skillCode={}, from={}, newVersion={}, userId={}",
            skillCode, versionTag, newVersionTag, userId);
        return toVersionDTO(newVersion);
    }

    // ======================== P3.2.1 Artifact 上传 ========================

    @Override
    @Transactional
    public SkillArtifactDTO uploadArtifact(String skillCode, String versionTag, MultipartFile file) {
        String userId = UserContext.getUserId();

        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Artifact file is required");
        }

        // P3.2.2: Artifact 内容校验
        validateArtifactFile(file);
        validateVersionTag(versionTag);

        SkillRegistryEntity skill = findSkillByCode(skillCode, userId);
        permissionChecker.checkWritePermission(userId, skill);

        // 查找或创建版本记录
        SkillVersionEntity version = skillVersionRepo.selectOne(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skill.getId())
                .eq(SkillVersionEntity::getVersionTag, versionTag)
        );

        if (version == null) {
            version = new SkillVersionEntity();
            version.setSkillId(skill.getId());
            version.setVersionTag(versionTag);
            version.setStatus("draft");
            version.setChangeLog("Draft version created by artifact upload");
            skillVersionRepo.insert(version);
        }

        // P3.2.5: 已发布版本 Artifact 禁止覆盖
        if ("staging".equals(version.getStatus()) || "production".equals(version.getStatus())
            || "rolled_back".equals(version.getStatus())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Cannot modify artifacts of published version: " + versionTag);
        }

        String fileName = file.getOriginalFilename();
        if (fileName == null || fileName.isBlank()) {
            fileName = "unnamed";
        }

        try {
            byte[] content = file.getBytes();
            String contentType = file.getContentType();

            // P3.2.3: MinIO 路径生成 {user_id}/{skill_code}/{version_tag}/{file_name}
            SkillArtifactStorageService.UploadResult result =
                artifactStorageService.uploadArtifact(userId, skillCode, versionTag, fileName, content, contentType);

            // P3.2.4: 记录 skill_artifact 表
            // 先删除同版本同名文件的旧记录（draft 状态允许覆盖）
            skillArtifactRepo.delete(
                new LambdaQueryWrapper<SkillArtifactEntity>()
                    .eq(SkillArtifactEntity::getSkillId, skill.getId())
                    .eq(SkillArtifactEntity::getVersionId, version.getId())
                    .eq(SkillArtifactEntity::getFileName, fileName)
            );

            SkillArtifactEntity artifact = new SkillArtifactEntity();
            artifact.setSkillId(skill.getId());
            artifact.setVersionId(version.getId());
            artifact.setArtifactType(detectArtifactType(fileName));
            artifact.setFileName(fileName);
            artifact.setFileSize((int) result.fileSize());
            artifact.setContentHash(result.contentHash());
            artifact.setMinioUrl(result.minioUrl());
            skillArtifactRepo.insert(artifact);

            recordAuditLog(skill.getId(), "ARTIFACT_UPLOAD",
                Map.of("action", "artifact_upload", "file_name", fileName, "version", versionTag));

            log.info("Uploaded skill artifact: skillCode={}, version={}, file={}, userId={}",
                skillCode, versionTag, fileName, userId);
            return toArtifactDTO(artifact);
        } catch (IOException e) {
            log.error("Failed to read artifact file: skillCode={}, version={}", skillCode, versionTag, e);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Failed to read artifact file", e);
        }
    }

    // ======================== 内部辅助方法 ========================

    private SkillRegistryEntity findSkillByCode(String skillCode, String userId) {
        SkillRegistryEntity entity = skillRegistryRepo.selectOne(
            new LambdaQueryWrapper<SkillRegistryEntity>()
                .eq(SkillRegistryEntity::getSkillCode, skillCode)
                .and(w -> w
                    .eq(SkillRegistryEntity::getUserId, userId)
                    .or()
                    .eq(SkillRegistryEntity::getTrustTier, "official")
                )
        );
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }
        return entity;
    }

    /**
     * P3.1.2: 版本号格式校验 MAJOR.MINOR.PATCH.
     */
    private void validateVersionTag(String versionTag) {
        if (versionTag == null || !VERSION_TAG_PATTERN.matcher(versionTag).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid version tag format, expected MAJOR.MINOR.PATCH: " + versionTag);
        }
    }

    /**
     * P3.2.2: Artifact 文件校验.
     */
    private void validateArtifactFile(MultipartFile file) {
        if (file.getSize() > MAX_ARTIFACT_SIZE_BYTES) {
            throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE,
                "Artifact file too large, max 10MB");
        }
        String fileName = file.getOriginalFilename();
        if (fileName == null || fileName.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Artifact file name is required");
        }
        // 禁止路径遍历
        if (fileName.contains("..") || fileName.contains("/") || fileName.contains("\\")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid artifact file name: " + fileName);
        }
        // 文件扩展名白名单校验（P7.4 安全审计修复）
        String lowerName = fileName.toLowerCase();
        if (!lowerName.endsWith(".json") && !lowerName.endsWith(".md")
                && !lowerName.endsWith(".py") && !lowerName.endsWith(".yaml")
                && !lowerName.endsWith(".yml") && !lowerName.endsWith(".txt")) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid artifact file type: only .json/.md/.py/.yaml/.yml/.txt are allowed");
        }
    }

    /**
     * P3.1.6: 计算版本内容哈希.
     * 规则：所有 Artifact 的 content_hash 按 file_name 排序后拼接，再 SHA-256.
     */
    private String computeVersionContentHash(List<SkillArtifactEntity> artifacts) {
        String combined = artifacts.stream()
            .sorted(Comparator.comparing(SkillArtifactEntity::getFileName))
            .map(a -> a.getFileName() + ":" + a.getContentHash())
            .collect(Collectors.joining(";"));

        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(combined.getBytes(StandardCharsets.UTF_8));
            return bytesToHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 algorithm not available", e);
        }
    }

    private String bytesToHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder();
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private String buildArtifactPath(String userId, String skillCode, String versionTag) {
        return String.format("%s/%s/%s/", userId, skillCode, versionTag);
    }

    private void markOtherProductionAsRolledBack(Long skillId, Long excludeVersionId) {
        List<SkillVersionEntity> productionVersions = skillVersionRepo.selectList(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skillId)
                .eq(SkillVersionEntity::getStatus, "production")
                .ne(SkillVersionEntity::getId, excludeVersionId)
        );

        for (SkillVersionEntity v : productionVersions) {
            v.setStatus("rolled_back");
            skillVersionRepo.updateById(v);
        }
    }

    /**
     * 生成下一个 PATCH 版本号.
     */
    private String generateNextPatchVersion(Long skillId, String baseVersionTag) {
        String[] parts = baseVersionTag.split("\\.");
        int major = Integer.parseInt(parts[0]);
        int minor = Integer.parseInt(parts[1]);
        int patch = Integer.parseInt(parts[2]);

        // 从 base 的 patch+1 开始尝试，避免冲突
        for (int i = 1; i < 1000; i++) {
            String candidate = major + "." + minor + "." + (patch + i);
            Long count = skillVersionRepo.selectCount(
                new LambdaQueryWrapper<SkillVersionEntity>()
                    .eq(SkillVersionEntity::getSkillId, skillId)
                    .eq(SkillVersionEntity::getVersionTag, candidate)
            );
            if (count == null || count == 0) {
                return candidate;
            }
        }
        throw new ResponseStatusException(HttpStatus.CONFLICT,
            "Cannot generate next patch version for: " + baseVersionTag);
    }

    private String detectArtifactType(String fileName) {
        String lower = fileName.toLowerCase();
        if (lower.equals("skill.json")) return "metadata";
        if (lower.equals("manifest.json")) return "manifest";
        if (lower.endsWith(".md")) return "prompt";
        if (lower.endsWith(".py")) return "tool_handler";
        if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "workflow_def";
        return "unknown";
    }

    private SkillVersionDTO toVersionDTO(SkillVersionEntity entity) {
        SkillVersionDTO dto = new SkillVersionDTO();
        dto.setId(entity.getId());
        dto.setSkillId(entity.getSkillId());
        dto.setVersionTag(entity.getVersionTag());
        dto.setContentHash(entity.getContentHash());
        dto.setArtifactPath(entity.getArtifactPath());
        dto.setChangeLog(entity.getChangeLog());
        dto.setPromotedBy(entity.getPromotedBy());
        dto.setPromotedAt(entity.getPromotedAt());
        dto.setStatus(entity.getStatus());
        dto.setCreatedAt(entity.getCreatedAt());
        return dto;
    }

    private SkillArtifactDTO toArtifactDTO(SkillArtifactEntity entity) {
        SkillArtifactDTO dto = new SkillArtifactDTO();
        dto.setId(entity.getId());
        dto.setSkillId(entity.getSkillId());
        dto.setVersionId(entity.getVersionId());
        dto.setArtifactType(entity.getArtifactType());
        dto.setFileName(entity.getFileName());
        dto.setFileSize(entity.getFileSize());
        dto.setContentHash(entity.getContentHash());
        dto.setMinioUrl(entity.getMinioUrl());
        dto.setCreatedAt(entity.getCreatedAt());
        return dto;
    }

    private void recordAuditLog(Long skillId, String operation, Map<String, Object> details) {
        try {
            SkillAuditLogEntity auditLog = new SkillAuditLogEntity();
            auditLog.setSkillId(skillId);
            auditLog.setOperation(operation);
            auditLog.setOperatorId(UserContext.getUserId());
            auditLog.setOperatorType("user");
            auditLog.setRequestId(UserContext.getRequestId());
            auditLog.setDetails(objectMapper.writeValueAsString(details));
            skillAuditLogRepo.insert(auditLog);
        } catch (JacksonException e) {
            log.error("Failed to serialize audit log details to JSON: skillId={}, operation={}, error={}",
                skillId, operation, e.getMessage());
        } catch (Exception e) {
            log.error("Failed to record skill audit log: skillId={}, operation={}, error={}",
                skillId, operation, e.getMessage());
        }
    }
}
