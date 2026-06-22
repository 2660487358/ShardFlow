package com.shardflow.config.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.dto.PermissionRequest;
import com.shardflow.config.dto.SkillPermissionDTO;
import com.shardflow.config.entity.SkillPermissionEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillPermissionRepository;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.support.SkillPermissionChecker;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Skill 权限配置服务.
 *
 * <p>Per Skills管理需求规格文档 FR-8.3 / IR-7 / 实施计划 P6.2.
 * <p>实现 RBAC+ABAC 权限模型的配置与查询：
 * <ul>
 *   <li>权限主体类型：user | role | team | tenant</li>
 *   <li>权限位掩码：1=读 2=写 4=执行 8=管理 16=审计（位掩码可组合）</li>
 * </ul>
 *
 * <p>支持 upsert 语义：同一 (skill_id, subject_type, subject_id) 组合唯一，
 * 已存在则更新 permission_mask，不存在则插入。
 *
 * <p>所有权限变更操作均记录审计日志（PERMISSION_CHANGE）。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillPermissionService {

    private final SkillPermissionRepository skillPermissionRepository;
    private final SkillRegistryRepository skillRegistryRepository;
    private final SkillPermissionChecker permissionChecker;
    private final SkillAuditService auditService;

    /**
     * 配置 Skill 权限（upsert 语义）.
     *
     * <p>FR-8.3: 配置 Skill 的访问权限.
     * <p>仅 Skill 的 owner 或具有 skill:admin 权限的用户可配置权限.
     *
     * @param skillCode Skill 编码
     * @param request   权限配置请求
     * @return 权限配置响应
     */
    @Transactional
    public SkillPermissionDTO configurePermission(String skillCode, PermissionRequest request) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 校验管理权限：仅 owner 或 admin 可配置权限
        permissionChecker.checkWritePermission(userId, skill);

        // 校验权限位掩码合法性（0~31）
        validatePermissionMask(request.getPermissionMask());

        // upsert：查询是否已存在相同 (skill_id, subject_type, subject_id) 的权限配置
        SkillPermissionEntity existing = skillPermissionRepository.selectOne(
                new LambdaQueryWrapper<SkillPermissionEntity>()
                        .eq(SkillPermissionEntity::getSkillId, skill.getId())
                        .eq(SkillPermissionEntity::getSubjectType, request.getSubjectType())
                        .eq(SkillPermissionEntity::getSubjectId, request.getSubjectId())
        );

        String operation;
        String details;
        SkillPermissionEntity entity;

        if (existing != null) {
            // 更新已有权限配置
            int oldMask = existing.getPermissionMask() != null ? existing.getPermissionMask() : 0;
            existing.setPermissionMask(request.getPermissionMask());
            skillPermissionRepository.updateById(existing);
            entity = existing;
            operation = "PERMISSION_UPDATE";
            details = String.format("subject=%s:%s, mask %d->%d",
                    request.getSubjectType(), request.getSubjectId(),
                    oldMask, request.getPermissionMask());
            log.info("SkillPermissionService: updated permission skill={} subject={}:{} mask={}",
                    skillCode, request.getSubjectType(), request.getSubjectId(), request.getPermissionMask());
        } else {
            // 新增权限配置
            entity = new SkillPermissionEntity();
            entity.setSkillId(skill.getId());
            entity.setSubjectType(request.getSubjectType());
            entity.setSubjectId(request.getSubjectId());
            entity.setPermissionMask(request.getPermissionMask());
            entity.setCreatedAt(Instant.now());
            skillPermissionRepository.insert(entity);
            operation = "PERMISSION_GRANT";
            details = String.format("subject=%s:%s, mask=%d",
                    request.getSubjectType(), request.getSubjectId(), request.getPermissionMask());
            log.info("SkillPermissionService: granted permission skill={} subject={}:{} mask={}",
                    skillCode, request.getSubjectType(), request.getSubjectId(), request.getPermissionMask());
        }

        // 记录审计日志
        auditService.recordAudit(
                skill.getId(),
                skillCode,
                operation,
                userId,
                details,
                0,
                0,
                true,
                ""
        );

        return toDTO(entity);
    }

    /**
     * 查询 Skill 的权限配置列表.
     *
     * <p>IR-10: 返回 Skill 的所有权限配置.
     * <p>仅 Skill 的 owner 或具有读权限的用户可查询.
     *
     * @param skillCode Skill 编码
     * @return 权限配置列表
     */
    public List<SkillPermissionDTO> listPermissions(String skillCode) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 校验读权限
        permissionChecker.checkReadPermission(userId, skill);

        List<SkillPermissionEntity> entities = skillPermissionRepository.selectList(
                new LambdaQueryWrapper<SkillPermissionEntity>()
                        .eq(SkillPermissionEntity::getSkillId, skill.getId())
                        .orderByAsc(SkillPermissionEntity::getSubjectType)
                        .orderByAsc(SkillPermissionEntity::getSubjectId)
        );

        return entities.stream()
                .map(this::toDTO)
                .collect(Collectors.toList());
    }

    /**
     * 删除 Skill 的权限配置.
     *
     * <p>FR-8.3: 撤销指定主体的权限.
     * <p>仅 Skill 的 owner 或具有 skill:admin 权限的用户可删除权限.
     *
     * @param skillCode    Skill 编码
     * @param subjectType  主体类型
     * @param subjectId    主体ID
     */
    @Transactional
    public void revokePermission(String skillCode, String subjectType, String subjectId) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = findSkill(skillCode);

        // 校验管理权限
        permissionChecker.checkWritePermission(userId, skill);

        // 校验主体类型
        validateSubjectType(subjectType);

        SkillPermissionEntity existing = skillPermissionRepository.selectOne(
                new LambdaQueryWrapper<SkillPermissionEntity>()
                        .eq(SkillPermissionEntity::getSkillId, skill.getId())
                        .eq(SkillPermissionEntity::getSubjectType, subjectType)
                        .eq(SkillPermissionEntity::getSubjectId, subjectId)
        );
        if (existing == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Permission not found: " + subjectType + ":" + subjectId);
        }

        skillPermissionRepository.deleteById(existing.getId());

        // 记录审计日志
        auditService.recordAudit(
                skill.getId(),
                skillCode,
                "PERMISSION_REVOKE",
                userId,
                String.format("subject=%s:%s, mask=%d",
                        subjectType, subjectId, existing.getPermissionMask()),
                0,
                0,
                true,
                ""
        );

        log.info("SkillPermissionService: revoked permission skill={} subject={}:{}",
                skillCode, subjectType, subjectId);
    }

    /**
     * 查询指定主体对 Skill 的权限位掩码.
     *
     * <p>供 SkillPermissionChecker 内部调用，支持四级主体聚合：
     * user < role < team < tenant（按优先级合并，user 优先）.
     *
     * @param skillId     Skill ID
     * @param subjectType 主体类型
     * @param subjectId   主体ID
     * @return 权限位掩码（无配置返回 0）
     */
    public int getPermissionMask(Long skillId, String subjectType, String subjectId) {
        SkillPermissionEntity entity = skillPermissionRepository.selectOne(
                new LambdaQueryWrapper<SkillPermissionEntity>()
                        .eq(SkillPermissionEntity::getSkillId, skillId)
                        .eq(SkillPermissionEntity::getSubjectType, subjectType)
                        .eq(SkillPermissionEntity::getSubjectId, subjectId)
        );

        return entity != null && entity.getPermissionMask() != null
                ? entity.getPermissionMask() : 0;
    }

    /**
     * 查询 Skill 的所有权限配置（内部调用，返回 Entity 列表）.
     *
     * @param skillId Skill ID
     * @return 权限配置 Entity 列表
     */
    public List<SkillPermissionEntity> listPermissionEntities(Long skillId) {
        return skillPermissionRepository.selectList(
                new LambdaQueryWrapper<SkillPermissionEntity>()
                        .eq(SkillPermissionEntity::getSkillId, skillId)
        );
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

    private void validatePermissionMask(Integer mask) {
        if (mask == null || mask < 0 || mask > 31) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid permission_mask: must be 0-31 (1=READ 2=WRITE 4=EXECUTE 8=MANAGE 16=AUDIT)");
        }
    }

    private void validateSubjectType(String subjectType) {
        if (subjectType == null || subjectType.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "subject_type cannot be blank");
        }
        if (!"user".equals(subjectType) && !"role".equals(subjectType)
                && !"team".equals(subjectType) && !"tenant".equals(subjectType)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                    "Invalid subject_type: must be user/role/team/tenant");
        }
    }

    private SkillPermissionDTO toDTO(SkillPermissionEntity entity) {
        SkillPermissionDTO dto = new SkillPermissionDTO();
        dto.setId(entity.getId());
        dto.setSkillId(entity.getSkillId());
        dto.setSubjectType(entity.getSubjectType());
        dto.setSubjectId(entity.getSubjectId());
        dto.setPermissionMask(entity.getPermissionMask());
        dto.setCreatedAt(entity.getCreatedAt());
        return dto;
    }
}
