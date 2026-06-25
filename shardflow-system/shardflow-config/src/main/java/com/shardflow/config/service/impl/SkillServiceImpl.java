package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shardflow.config.dto.*;
import com.shardflow.config.entity.*;
import com.shardflow.config.repository.*;
import com.shardflow.config.service.SkillCacheEvictor;
import com.shardflow.config.service.SkillArtifactStorageService;
import com.shardflow.config.service.SkillService;
import com.shardflow.config.support.SkillCodeGenerator;
import com.shardflow.config.support.SkillEntityConverter;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.config.support.SkillStateMachine;
import com.shardflow.usercontext.context.UserContext;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.*;
import java.util.stream.Collectors;

/**
 * Skill 生命周期管理服务实现.
 *
 * <p>Per Skills管理需求规格文档 FR-1 / FR-4 / 实施计划 P2.2~P2.4.
 * <p>实现 Skill 的 CRUD、状态切换、分类搜索、基础权限控制。
 * <p>缓存策略: 写操作后调用 SkillCacheEvictor 失效缓存（FR-9）。
 * <p>审计日志: 所有 CRUD/状态切换操作写入 skill_audit_log（FR-8.7）。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillServiceImpl implements SkillService {

    private final SkillRegistryRepository skillRegistryRepo;
    private final SkillVersionRepository skillVersionRepo;
    private final SkillArtifactRepository skillArtifactRepo;
    private final AgentSkillBindingRepository agentSkillBindingRepo;
    private final SkillPermissionRepository skillPermissionRepo;
    private final SkillAuditLogRepository skillAuditLogRepo;
    private final SkillCacheEvictor cacheEvictor;
    private final SkillArtifactStorageService artifactStorageService;
    private final SkillCodeGenerator codeGenerator;
    private final SkillPermissionChecker permissionChecker;
    private final SkillEntityConverter converter;
    private final ObjectMapper objectMapper;

    // ======================== P2.2.1 创建 Skill ========================

    @Override
    public SkillDTO createSkill(CreateSkillRequest request) {
        String userId = UserContext.getUserId();

        // P2.2.10: official Skill 保护
        permissionChecker.checkCreatePermission(userId, request.getTrustTier());

        // P2.2.8: 名称唯一性校验（user_id + trust_tier 维度）
        checkNameUniqueness(userId, request.getSkillName(), request.getTrustTier(), null);

        // P2.2.11: 生成 skill_code
        String skillCode = codeGenerator.generate();

        // 构建 Entity
        SkillRegistryEntity entity = converter.fromCreateRequest(request, userId);
        entity.setSkillCode(skillCode);

        try {
            skillRegistryRepo.insert(entity);
        } catch (DuplicateKeyException e) {
            // 并发场景下可能触发唯一约束异常
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Skill name already exists or skill_code collision");
        }

        // 记录审计日志
        recordAuditLog(entity.getId(), "CREATE", Map.of("action", "create", "skill_name", entity.getSkillName()));

        // 缓存失效
        cacheEvictor.evictOnSkillChange(userId, skillCode);

        log.info("Created skill: skillCode={}, userId={}", skillCode, userId);
        return converter.toDTO(entity);
    }

    // ======================== P2.2.2 列表查询 ========================

    @Override
    public Map<String, Object> listSkills(SkillQueryRequest query) {
        String userId = UserContext.getUserId();

        LambdaQueryWrapper<SkillRegistryEntity> wrapper = new LambdaQueryWrapper<>();

        // 可见性: 用户自己的 Skill + 所有 official Skill（FR-1.2 / NFR-3.1）
        wrapper.and(w -> w
            .eq(SkillRegistryEntity::getUserId, userId)
            .or()
            .eq(SkillRegistryEntity::getTrustTier, "official")
        );

        // P2.3.2: 关键词搜索（skill_name OR description 模糊匹配）
        if (query.getKeyword() != null && !query.getKeyword().isBlank()) {
            String kw = query.getKeyword().trim();
            wrapper.and(w -> w
                .like(SkillRegistryEntity::getSkillName, kw)
                .or()
                .like(SkillRegistryEntity::getDescription, kw)
            );
        }

        // P2.3.3: 状态筛选
        if (query.getStatus() != null && !query.getStatus().isBlank()) {
            wrapper.eq(SkillRegistryEntity::getStatus, query.getStatus());
        }

        // P2.3.4: 默认排序 created_at DESC
        wrapper.orderByDesc(SkillRegistryEntity::getCreatedAt);

        // 分页查询
        Page<SkillRegistryEntity> page = skillRegistryRepo.selectPage(
            new Page<>(query.getPage(), query.getSize()),
            wrapper
        );

        List<SkillDTO> skills = page.getRecords().stream()
            .map(converter::toDTO)
            .collect(Collectors.toList());

        return Map.of(
            "skills", skills,
            "total", page.getTotal(),
            "page", query.getPage(),
            "size", query.getSize()
        );
    }

    // ======================== P2.2.3 详情查询 ========================

    @Override
    public SkillDetailDTO getSkillDetail(String skillCode) {
        String userId = UserContext.getUserId();

        SkillRegistryEntity entity = findEntityByCode(skillCode, userId);
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }

        // 权限校验
        permissionChecker.checkReadPermission(userId, entity);

        // 查询关联 Agent 列表
        List<AgentSkillBindingEntity> bindings = agentSkillBindingRepo.selectList(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getSkillId, entity.getId())
        );

        // 查询版本历史
        List<SkillVersionEntity> versions = skillVersionRepo.selectList(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, entity.getId())
                .orderByDesc(SkillVersionEntity::getCreatedAt)
        );

        return converter.toDetailDTO(entity, bindings, versions);
    }

    // ======================== P2.2.4 更新 Skill ========================

    @Override
    public SkillDTO updateSkill(String skillCode, UpdateSkillRequest request) {
        String userId = UserContext.getUserId();

        SkillRegistryEntity entity = findEntityByCode(skillCode, userId);
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }

        // 权限校验
        permissionChecker.checkWritePermission(userId, entity);

        // 如果修改了 skillName，检查名称唯一性
        if (request.getSkillName() != null && !request.getSkillName().equals(entity.getSkillName())) {
            checkNameUniqueness(userId, request.getSkillName(),
                request.getTrustTier() != null ? request.getTrustTier() : entity.getTrustTier(),
                entity.getId());
        }

        // 如果修改了 trustTier，检查创建权限
        if (request.getTrustTier() != null && !request.getTrustTier().equals(entity.getTrustTier())) {
            permissionChecker.checkCreatePermission(userId, request.getTrustTier());
        }

        // 保存变更前快照
        String beforeSnapshot = "status=" + entity.getStatus() + ", name=" + entity.getSkillName();

        // 选择性更新
        converter.mergeUpdates(entity, request);
        entity.setUpdatedBy(userId);

        try {
            skillRegistryRepo.updateById(entity);
        } catch (DuplicateKeyException e) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Skill name already exists");
        }

        // 记录审计日志
        recordAuditLog(entity.getId(), "UPDATE", Map.of(
            "action", "update",
            "before_status", entity.getStatus() != null ? entity.getStatus() : "",
            "before_name", beforeSnapshot,
            "after_name", entity.getSkillName()
        ));

        // 缓存失效
        cacheEvictor.evictOnSkillChange(userId, skillCode);

        log.info("Updated skill: skillCode={}, userId={}", skillCode, userId);
        return converter.toDTO(entity);
    }

    // ======================== P2.2.5 删除 Skill（级联删除） ========================

    @Override
    @Transactional
    public void deleteSkill(String skillCode) {
        String userId = UserContext.getUserId();

        SkillRegistryEntity entity = findEntityByCode(skillCode, userId);
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }

        // 权限校验
        permissionChecker.checkDeletePermission(userId, entity);

        Long skillId = entity.getId();

        // 级联删除（从依赖方到主表）

        // 1. 删除 Agent-Skill 绑定
        agentSkillBindingRepo.delete(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getSkillId, skillId)
        );

        // 2. 删除 Skill Artifact（先查后删，用于 MinIO 清理）
        List<SkillArtifactEntity> artifacts = skillArtifactRepo.selectList(
            new LambdaQueryWrapper<SkillArtifactEntity>()
                .eq(SkillArtifactEntity::getSkillId, skillId)
        );
        if (!artifacts.isEmpty()) {
            skillArtifactRepo.delete(
                new LambdaQueryWrapper<SkillArtifactEntity>()
                    .eq(SkillArtifactEntity::getSkillId, skillId)
            );
            // 异步删除 MinIO 文件（容错，失败不回滚）
            artifacts.forEach(a -> {
                try {
                    artifactStorageService.deleteArtifact(a.getMinioUrl());
                } catch (Exception e) {
                    log.warn("Failed to delete MinIO artifact: {}, error: {}",
                        a.getMinioUrl(), e.getMessage());
                }
            });
        }

        // 3. 删除 Skill Version
        skillVersionRepo.delete(
            new LambdaQueryWrapper<SkillVersionEntity>()
                .eq(SkillVersionEntity::getSkillId, skillId)
        );

        // 4. 删除 Skill Permission
        skillPermissionRepo.delete(
            new LambdaQueryWrapper<SkillPermissionEntity>()
                .eq(SkillPermissionEntity::getSkillId, skillId)
        );

        // 5. 删除 Skill Registry 主记录
        skillRegistryRepo.deleteById(skillId);

        // 6. 记录审计日志（追加，不删除）
        recordAuditLog(skillId, "DELETE", Map.of(
            "action", "delete",
            "skill_code", entity.getSkillCode(),
            "skill_name", entity.getSkillName()
        ));

        // 7. 缓存失效
        cacheEvictor.evictOnSkillChange(userId, skillCode);

        log.info("Deleted skill: skillCode={}, userId={}", skillCode, userId);
    }

    // ======================== P2.2.6 状态切换 ========================

    @Override
    public SkillDTO changeStatus(String skillCode, SkillStatusRequest request) {
        String userId = UserContext.getUserId();

        SkillRegistryEntity entity = findEntityByCode(skillCode, userId);
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }

        // 权限校验
        permissionChecker.checkWritePermission(userId, entity);

        // 状态机校验
        SkillStateMachine.checkTransition(entity.getStatus(), request.getStatus());

        // 保存变更前快照
        String beforeStatus = entity.getStatus();

        // 更新状态
        entity.setStatus(request.getStatus());
        entity.setUpdatedBy(userId);
        skillRegistryRepo.updateById(entity);

        // 记录审计日志
        recordAuditLog(entity.getId(), "STATUS_CHANGE", Map.of(
            "action", "status_change",
            "from", beforeStatus,
            "to", request.getStatus()
        ));

        // 缓存失效
        cacheEvictor.evictOnSkillChange(userId, skillCode);

        log.info("Changed skill status: skillCode={}, {} -> {}, userId={}",
            skillCode, beforeStatus, request.getStatus(), userId);
        return converter.toDTO(entity);
    }

    // ======================== 内部辅助方法 ========================

    /**
     * 根据 skillCode 查询用户可见的 Skill 实体.
     * 可见性: user_id = userId OR trust_tier = 'official'
     */
    private SkillRegistryEntity findEntityByCode(String skillCode, String userId) {
        return skillRegistryRepo.selectOne(
            new LambdaQueryWrapper<SkillRegistryEntity>()
                .eq(SkillRegistryEntity::getSkillCode, skillCode)
                .and(w -> w
                    .eq(SkillRegistryEntity::getUserId, userId)
                    .or()
                    .eq(SkillRegistryEntity::getTrustTier, "official")
                )
        );
    }

    /**
     * 名称唯一性校验.
     * P2.2.8 / 10.7: 同一 user_id + trust_tier 下 skill_name 唯一.
     *
     * @param userId       用户ID
     * @param skillName    Skill 名称
     * @param trustTier    信任等级
     * @param excludeId    排除的 Skill ID（更新时排除自身），创建时传 null
     */
    private void checkNameUniqueness(String userId, String skillName, String trustTier, Long excludeId) {
        LambdaQueryWrapper<SkillRegistryEntity> wrapper = new LambdaQueryWrapper<SkillRegistryEntity>()
            .eq(SkillRegistryEntity::getUserId, userId)
            .eq(SkillRegistryEntity::getSkillName, skillName);

        if (trustTier != null) {
            wrapper.eq(SkillRegistryEntity::getTrustTier, trustTier);
        }
        if (excludeId != null) {
            wrapper.ne(SkillRegistryEntity::getId, excludeId);
        }

        Long count = skillRegistryRepo.selectCount(wrapper);
        if (count != null && count > 0) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Skill name already exists: " + skillName);
        }
    }

    /**
     * 记录 Skill 操作审计日志.
     * FR-8.7: 所有 CRUD/状态切换操作均记录审计日志.
     * 审计日志写入失败不阻断主流程。
     *
     * @param skillId   Skill ID
     * @param operation 操作类型: CREATE|UPDATE|DELETE|STATUS_CHANGE
     * @param details   操作详情（Map，将被序列化为 JSON 写入 JSONB 列）
     */
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
