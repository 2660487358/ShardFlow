package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.config.dto.ImportResult;
import com.shardflow.config.dto.SkillImportRequest;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.service.SkillCacheEvictor;
import com.shardflow.config.service.SkillImportService;
import com.shardflow.config.support.SkillCodeGenerator;
import com.shardflow.config.support.SkillEntityConverter;
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
import java.util.Map;

/**
 * Skill 导入服务实现.
 *
 * <p>Per Skills管理需求规格文档 FR-3 / 实施计划 P3.3.
 * <p>支持单对象与数组 JSON 格式导入，逐条校验、同名跳过、返回导入统计。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillImportServiceImpl implements SkillImportService {

    private static final long MAX_IMPORT_FILE_SIZE_BYTES = 5 * 1024 * 1024L; // 5MB
    private static final int MAX_SKILL_NAME_LENGTH = 128;
    private static final int MAX_DESCRIPTION_LENGTH = 2000;

    private final ObjectMapper objectMapper;
    private final SkillRegistryRepository skillRegistryRepo;
    private final SkillCodeGenerator codeGenerator;
    private final SkillEntityConverter converter;
    private final SkillCacheEvictor cacheEvictor;
    private final SkillPermissionChecker permissionChecker;

    @Override
    @Transactional
    public ImportResult importSkills(MultipartFile file) {
        String userId = UserContext.getUserId();

        // FR-3.6 / P3.3.1: 文件大小限制 5MB
        if (file == null || file.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Import file is required");
        }
        if (file.getSize() > MAX_IMPORT_FILE_SIZE_BYTES) {
            throw new ResponseStatusException(HttpStatusCode.valueOf(413),
                "Import file too large, max 5MB");
        }

        // P3.3.2: 解析 JSON（单对象或数组）
        List<SkillImportRequest> requests = parseImportFile(file);
        ImportResult result = new ImportResult();

        for (SkillImportRequest request : requests) {
            ImportResult.ImportDetail detail = importSingleSkill(userId, request);
            result.getDetails().add(detail);
            switch (detail.getStatus()) {
                case "created" -> result.incrementCreated();
                case "skipped" -> result.incrementSkipped();
                default -> result.incrementFailed();
            }
        }

        if (result.getCreated() > 0) {
            cacheEvictor.evictSkillList(userId);
            cacheEvictor.evictCategories(userId);
        }

        log.info("Imported skills: userId={}, created={}, skipped={}, failed={}",
            userId, result.getCreated(), result.getSkipped(), result.getFailed());
        return result;
    }

    /**
     * P3.3.2: 解析导入文件，支持单对象和数组.
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

    /**
     * 导入单个 Skill.
     */
    private ImportResult.ImportDetail importSingleSkill(String userId, SkillImportRequest request) {
        String skillName = request.getSkillName();

        // P3.3.3: 逐条校验
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

        // P3.3.4: 同名跳过（user_id + trust_tier 维度 skill_name 唯一）
        if (existsByName(userId, skillName, trustTier)) {
            return new ImportResult.ImportDetail(skillName, "skipped", null,
                "Skill with same name already exists");
        }

        try {
            SkillRegistryEntity entity = converter.fromCreateRequest(toCreateRequest(request), userId);
            entity.setSkillCode(codeGenerator.generate());
            // P3.3.5: 标记 source=IMPORTED
            entity.setSource("IMPORTED");
            skillRegistryRepo.insert(entity);

            return new ImportResult.ImportDetail(skillName, "created", entity.getSkillCode(), null);
        } catch (DuplicateKeyException e) {
            log.warn("Skill code collision during import: name={}", skillName);
            return new ImportResult.ImportDetail(skillName, "failed", null,
                "Skill code collision, please retry");
        }
    }

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
        dst.setCategory(src.getCategory());
        dst.setTriggerKeywords(src.getTriggerKeywords());
        dst.setInputSchema(src.getInputSchema());
        dst.setOutputSchema(src.getOutputSchema());
        dst.setCostEstimate(src.getCostEstimate());
        dst.setConfig(src.getConfig());
        dst.setTags(src.getTags());
        return dst;
    }
}
