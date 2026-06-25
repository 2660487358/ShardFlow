package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.config.dto.ImportResult;
import com.shardflow.config.dto.SkillImportRequest;
import com.shardflow.config.entity.SkillArtifactEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.entity.SkillVersionEntity;
import com.shardflow.config.repository.SkillArtifactRepository;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.repository.SkillVersionRepository;
import com.shardflow.config.service.SkillArtifactStorageService;
import com.shardflow.config.service.SkillCacheEvictor;
import com.shardflow.config.service.SkillImportService;
import com.shardflow.config.support.ParsedSkillPackage;
import com.shardflow.config.support.SkillCodeGenerator;
import com.shardflow.config.support.SkillEntityConverter;
import com.shardflow.config.support.SkillPackageParser;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Skill 导入服务实现.
 *
 * <p>Per Skills管理需求规格文档 FR-3 / 实施计划 P3.
 * <p>支持三种导入格式：
 * <ul>
 *   <li>JSON 文件（单对象或数组）— 兼容原有导入方式</li>
 *   <li>ZIP 压缩包 — 支持 .zip 格式</li>
 *   <li>TAR.GZ 压缩包 — 支持 .tar.gz / .tgz 格式</li>
 * </ul>
 *
 * <p>压缩包导入自动完成完整流程：解析 → 创建 skill_registry → 创建 skill_version →
 * 上传 Artifact 到 MinIO → 创建 skill_artifact 记录。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillImportServiceImpl implements SkillImportService {

    /** 压缩包导入文件大小限制 50MB（与 application.yml 一致） */
    private static final long MAX_ARCHIVE_SIZE_BYTES = 50 * 1024 * 1024L;

    /** JSON 导入文件大小限制 5MB（兼容原有约束） */
    private static final long MAX_JSON_SIZE_BYTES = 5 * 1024 * 1024L;

    private static final int MAX_SKILL_NAME_LENGTH = 128;
    private static final int MAX_DESCRIPTION_LENGTH = 2000;

    private final ObjectMapper objectMapper;
    private final SkillRegistryRepository skillRegistryRepo;
    private final SkillVersionRepository skillVersionRepo;
    private final SkillArtifactRepository skillArtifactRepo;
    private final SkillCodeGenerator codeGenerator;
    private final SkillEntityConverter converter;
    private final SkillCacheEvictor cacheEvictor;
    private final SkillPermissionChecker permissionChecker;
    private final SkillPackageParser packageParser;
    private final SkillArtifactStorageService artifactStorageService;

    @Override
    @Transactional
    public ImportResult importSkills(MultipartFile file) {
        String userId = UserContext.getUserId();

        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Import file is required");
        }

        String filename = file.getOriginalFilename();
        boolean isArchive = SkillPackageParser.isArchiveFormat(filename);

        // 文件大小限制：压缩包 50MB，JSON 5MB
        long sizeLimit = isArchive ? MAX_ARCHIVE_SIZE_BYTES : MAX_JSON_SIZE_BYTES;
        if (file.getSize() > sizeLimit) {
            throw new ResponseStatusException(HttpStatusCode.valueOf(413),
                "Import file too large, max " + (sizeLimit / 1024 / 1024) + "MB");
        }

        if (isArchive) {
            return importFromArchive(userId, file);
        } else {
            return importFromJson(userId, file);
        }
    }

    // ======================== JSON 导入（原有逻辑） ========================

    private ImportResult importFromJson(String userId, MultipartFile file) {
        List<SkillImportRequest> requests = parseImportFile(file);
        ImportResult result = new ImportResult();

        for (SkillImportRequest request : requests) {
            ImportResult.ImportDetail detail = importSingleSkill(userId, request, null);
            result.getDetails().add(detail);
            switch (detail.getStatus()) {
                case "created" -> result.incrementCreated();
                case "skipped" -> result.incrementSkipped();
                default -> result.incrementFailed();
            }
        }

        if (result.getCreated() > 0) {
            cacheEvictor.evictSkillList(userId);
        }

        log.info("Imported skills from JSON: userId={}, created={}, skipped={}, failed={}",
            userId, result.getCreated(), result.getSkipped(), result.getFailed());
        return result;
    }

    /**
     * P3.3.2: 解析导入 JSON 文件，支持单对象和数组.
     */
    private List<SkillImportRequest> parseImportFile(MultipartFile file) {
        try {
            String json = new String(file.getBytes());
            json = json.trim();
            if (json.startsWith("[")) {
                return objectMapper.readValue(json, new TypeReference<List<SkillImportRequest>>() {});
            } else {
                SkillImportRequest single = objectMapper.readValue(json, SkillImportRequest.class);
                List<SkillImportRequest> list = new ArrayList<>();
                list.add(single);
                return list;
            }
        } catch (IOException e) {
            log.error("Failed to parse import JSON file", e);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid JSON format: " + e.getMessage());
        }
    }

    // ======================== 压缩包导入（P3.5 新增） ========================

    /**
     * 从压缩包导入 Skill.
     *
     * <p>流程：
     * <ol>
     *   <li>调用 {@link SkillPackageParser} 解析压缩包</li>
     *   <li>校验元数据必需字段</li>
     *   <li>权限校验（不能创建 official Skill）</li>
     *   <li>同名跳过（user_id + trust_tier + skill_name 维度）</li>
     *   <li>创建 skill_registry 记录（source=IMPORTED）</li>
     *   <li>创建 skill_version 初始版本记录</li>
     *   <li>遍历 artifacts 上传到 MinIO</li>
     *   <li>创建 skill_artifact 记录</li>
     *   <li>更新 skill_registry.current_version</li>
     * </ol>
     */
    private ImportResult importFromArchive(String userId, MultipartFile file) {
        ParsedSkillPackage pkg;
        try {
            pkg = packageParser.parse(file);
        } catch (IllegalArgumentException e) {
            // 压缩包格式错误、损坏、为空、缺少元数据等
            log.warn("Skill package parse failed: userId={}, file={}, error={}",
                userId, file.getOriginalFilename(), e.getMessage());
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, e.getMessage());
        } catch (IOException e) {
            log.error("Skill package IO error: userId={}, file={}",
                userId, file.getOriginalFilename(), e);
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "压缩包读取失败，文件可能已损坏: " + e.getMessage());
        }

        ImportResult result = new ImportResult();
        ImportResult.ImportDetail detail = importSingleSkill(userId, pkg.getMetadata(), pkg);
        result.getDetails().add(detail);

        switch (detail.getStatus()) {
            case "created" -> {
                result.incrementCreated();
                result.setArtifactsUploaded(detail.getArtifacts().size());
                result.setVersionCreated(detail.getVersion());
            }
            case "skipped" -> result.incrementSkipped();
            default -> result.incrementFailed();
        }

        if (result.getCreated() > 0) {
            cacheEvictor.evictSkillList(userId);
        }

        log.info("Imported skill from archive: userId={}, sourceType={}, created={}, artifacts={}, version={}",
            userId, pkg.getSourceType(), result.getCreated(),
            result.getArtifactsUploaded(), result.getVersionCreated());
        return result;
    }

    /**
     * 导入单个 Skill（统一入口，支持 JSON 和压缩包）.
     *
     * @param userId   用户ID
     * @param request  Skill 元数据
     * @param pkg      压缩包解析结果（JSON 导入时为 null）
     */
    private ImportResult.ImportDetail importSingleSkill(String userId,
                                                         SkillImportRequest request,
                                                         ParsedSkillPackage pkg) {
        String skillName = request.getSkillName();

        // 元数据校验
        String validationError = validateSkillImportRequest(request);
        if (validationError != null) {
            return new ImportResult.ImportDetail(skillName, "failed", null, validationError);
        }

        // 权限校验：导入时不能创建 official Skill
        String trustTier = request.getTrustTier() != null ? request.getTrustTier() : "personal";
        try {
            permissionChecker.checkCreatePermission(userId, trustTier);
        } catch (ResponseStatusException e) {
            return new ImportResult.ImportDetail(skillName, "failed", null,
                "No permission to create " + trustTier + " skill");
        }

        // 同名跳过（user_id + trust_tier 维度 skill_name 唯一）
        if (existsByName(userId, skillName, trustTier)) {
            return new ImportResult.ImportDetail(skillName, "skipped", null,
                "Skill with same name already exists");
        }

        try {
            // 1. 创建 skill_registry 记录
            SkillRegistryEntity entity = converter.fromCreateRequest(toCreateRequest(request), userId);
            entity.setSkillCode(codeGenerator.generate());
            entity.setSource("IMPORTED");
            skillRegistryRepo.insert(entity);

            ImportResult.ImportDetail detail = new ImportResult.ImportDetail(
                skillName, "created", entity.getSkillCode(), null);

            // 2. 压缩包导入：创建版本 + 上传 Artifact
            if (pkg != null && pkg.getArtifacts() != null && !pkg.getArtifacts().isEmpty()) {
                String versionTag = pkg.getVersion() != null ? pkg.getVersion() : "1.0.0";
                List<String> uploadedArtifacts = createVersionAndUploadArtifacts(
                    userId, entity, versionTag, pkg.getArtifacts());
                detail.setArtifacts(uploadedArtifacts);
                detail.setVersion(versionTag);
            }

            return detail;
        } catch (DuplicateKeyException e) {
            log.warn("Skill code collision during import: name={}", skillName);
            return new ImportResult.ImportDetail(skillName, "failed", null,
                "Skill code collision, please retry");
        } catch (RuntimeException e) {
            log.error("Skill import failed: name={}, error={}", skillName, e.getMessage(), e);
            return new ImportResult.ImportDetail(skillName, "failed", null,
                "Import failed: " + e.getMessage());
        }
    }

    /**
     * 创建版本记录并上传 Artifact 到 MinIO.
     *
     * @param userId     用户ID
     * @param entity     已创建的 skill_registry 实体
     * @param versionTag 版本标签
     * @param artifacts  Artifact 文件映射（文件名 → 内容）
     * @return 上传成功的 Artifact 文件名列表
     */
    private List<String> createVersionAndUploadArtifacts(String userId,
                                                          SkillRegistryEntity entity,
                                                          String versionTag,
                                                          Map<String, byte[]> artifacts) {
        List<String> uploadedFiles = new ArrayList<>();

        // 1. 创建 skill_version 记录
        SkillVersionEntity versionEntity = new SkillVersionEntity();
        versionEntity.setSkillId(entity.getId());
        versionEntity.setVersionTag(versionTag);
        versionEntity.setStatus("draft");
        versionEntity.setChangeLog("Imported from package");
        versionEntity.setArtifactPath(String.format("%s/%s/%s",
            userId, entity.getSkillCode(), versionTag));
        skillVersionRepo.insert(versionEntity);

        // 2. 遍历上传 Artifact
        for (Map.Entry<String, byte[]> entry : artifacts.entrySet()) {
            String fileName = entry.getKey();
            byte[] content = entry.getValue();
            String artifactType = resolveArtifactType(fileName);
            String contentType = resolveContentType(fileName);

            try {
                SkillArtifactStorageService.UploadResult uploadResult = artifactStorageService.uploadArtifact(
                    userId, entity.getSkillCode(), versionTag, fileName, content, contentType);

                // 创建 skill_artifact 记录
                SkillArtifactEntity artifactEntity = new SkillArtifactEntity();
                artifactEntity.setSkillId(entity.getId());
                artifactEntity.setVersionId(versionEntity.getId());
                artifactEntity.setArtifactType(artifactType);
                artifactEntity.setFileName(fileName);
                artifactEntity.setFileSize(content.length);
                artifactEntity.setContentHash(uploadResult.contentHash());
                artifactEntity.setMinioUrl(uploadResult.minioUrl());
                skillArtifactRepo.insert(artifactEntity);

                uploadedFiles.add(fileName);
                log.debug("Uploaded artifact: skill={}, version={}, file={}, type={}",
                    entity.getSkillCode(), versionTag, fileName, artifactType);
            } catch (Exception e) {
                log.error("Failed to upload artifact: skill={}, file={}, error={}",
                    entity.getSkillCode(), fileName, e.getMessage());
                // 单个 Artifact 上传失败不中断整体流程，继续上传其他文件
            }
        }

        // 3. 更新 skill_registry.current_version
        if (!uploadedFiles.isEmpty()) {
            SkillRegistryEntity update = new SkillRegistryEntity();
            update.setId(entity.getId());
            update.setCurrentVersion(versionTag);
            skillRegistryRepo.updateById(update);
            entity.setCurrentVersion(versionTag);
        }

        return uploadedFiles;
    }

    /**
     * 根据文件名解析 Artifact 类型.
     * 映射规则：skill.json→metadata, manifest.json→manifest, SKILL.md/skill.md/prompt.md→prompt,
     * tool.py→tool_handler, workflow.yaml/yml→workflow_def
     */
    private String resolveArtifactType(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        if (lower.equals("skill.json")) return "metadata";
        if (lower.equals("manifest.json")) return "manifest";
        if (lower.equals("skill.md") || lower.equals("prompt.md")) return "prompt";
        if (lower.equals("tool.py")) return "tool_handler";
        if (lower.equals("workflow.yaml") || lower.equals("workflow.yml")) return "workflow_def";
        return "metadata"; // 默认类型
    }

    /**
     * 根据文件扩展名解析 MIME Content-Type.
     */
    private String resolveContentType(String fileName) {
        String lower = fileName.toLowerCase(Locale.ROOT);
        if (lower.endsWith(".md")) return "text/markdown";
        if (lower.endsWith(".py")) return "text/x-python";
        if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "application/yaml";
        if (lower.endsWith(".json")) return "application/json";
        return "application/octet-stream";
    }

    // ======================== 校验与辅助 ========================

    /**
     * P3.3.3: 校验导入条目.
     */
    private String validateSkillImportRequest(SkillImportRequest request) {
        if (request.getSkillName() == null || request.getSkillName().isBlank()) {
            return "Skill name is required";
        }
        if (request.getSkillName().length() > MAX_SKILL_NAME_LENGTH) {
            return "Skill name exceeds 128 characters";
        }
        if (request.getDescription() != null
            && request.getDescription().length() > MAX_DESCRIPTION_LENGTH) {
            return "Description exceeds 2000 characters";
        }
        if (request.getSkillType() != null
            && !request.getSkillType().matches("prompt|tool|hybrid|workflow")) {
            return "Invalid skill_type, expected prompt/tool/hybrid/workflow";
        }
        if (request.getTrustTier() != null
            && !request.getTrustTier().matches("official|team|personal")) {
            return "Invalid trust_tier, expected official/team/personal";
        }
        return null;
    }

    private boolean existsByName(String userId, String skillName, String trustTier) {
        LambdaQueryWrapper<SkillRegistryEntity> wrapper = new LambdaQueryWrapper<SkillRegistryEntity>()
            .eq(SkillRegistryEntity::getUserId, userId)
            .eq(SkillRegistryEntity::getSkillName, skillName);
        if (trustTier != null) {
            wrapper.eq(SkillRegistryEntity::getTrustTier, trustTier);
        }
        Long count = skillRegistryRepo.selectCount(wrapper);
        return count != null && count > 0;
    }

    /**
     * 将导入请求转换为创建请求以复用转换器.
     */
    private com.shardflow.config.dto.CreateSkillRequest toCreateRequest(SkillImportRequest src) {
        com.shardflow.config.dto.CreateSkillRequest dst = new com.shardflow.config.dto.CreateSkillRequest();
        dst.setSkillName(src.getSkillName());
        dst.setDescription(src.getDescription());
        dst.setSkillType(src.getSkillType());
        dst.setTrustTier(src.getTrustTier());
        dst.setTriggerKeywords(src.getTriggerKeywords());
        dst.setInputSchema(src.getInputSchema());
        dst.setOutputSchema(src.getOutputSchema());
        dst.setCostEstimate(src.getCostEstimate());
        dst.setConfig(src.getConfig());
        dst.setTags(src.getTags());
        return dst;
    }
}
