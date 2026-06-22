package com.shardflow.config.support;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.entity.SkillPermissionEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillPermissionRepository;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;

/**
 * Skill 权限校验器.
 *
 * <p>Per Skills管理需求规格文档 NFR-3 / FR-1.7 / FR-8.3 / 实施计划 P2.4 / P6.2.
 *
 * <p>支持双层权限校验：
 * <ul>
 *   <li>基础权限模型（P2.4）：基于 trustTier 的简单校验
 *       <ul>
 *         <li>personal: 仅 owner 可读写</li>
 *         <li>team: owner/admin 可写</li>
 *         <li>official: 全员可读，仅安全团队（skill:official:write 权限）可写</li>
 *       </ul>
 *   </li>
 *   <li>RBAC+ABAC 权限模型（P6.2）：基于位掩码的细粒度校验
 *       <ul>
 *         <li>主体类型：user | role | team | tenant</li>
 *         <li>权限位掩码：1=READ 2=WRITE 4=EXECUTE 8=MANAGE 16=AUDIT</li>
 *         <li>四级主体聚合：user < role < team < tenant（按优先级合并，user 优先）</li>
 *       </ul>
 *   </li>
 * </ul>
 *
 * <p>权限来源:
 * <ul>
 *   <li>UserContext.getPermissions() (ThreadLocal)：基础权限标识列表（如 skill:official:write）</li>
 *   <li>SkillPermissionService：RBAC+ABAC 权限配置（skill_permission 表）</li>
 * </ul>
 *
 * <p>与 MCP 模块 McpPermissionChecker 模式一致。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SkillPermissionChecker {

    /** 安全团队写权限标识 */
    private static final String PERM_OFFICIAL_WRITE = "skill:official:write";
    /** 管理员权限标识 */
    private static final String PERM_ADMIN = "skill:admin";

    // ── RBAC+ABAC 权限位掩码常量 ──
    public static final int MASK_READ = 1;
    public static final int MASK_WRITE = 2;
    public static final int MASK_EXECUTE = 4;
    public static final int MASK_MANAGE = 8;
    public static final int MASK_AUDIT = 16;

    private final SkillPermissionRepository skillPermissionRepository;

    // ======================== 基础权限模型（P2.4）========================

    /**
     * 校验创建 Skill 的权限.
     * P2.2.10 / FR-1.7: 普通用户不能创建 official Skill.
     *
     * @param userId    当前用户ID
     * @param trustTier 目标信任等级
     */
    public void checkCreatePermission(String userId, String trustTier) {
        if ("official".equals(trustTier)) {
            if (!hasPermission(PERM_OFFICIAL_WRITE)) {
                log.warn("User {} attempted to create official skill without permission", userId);
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Only security team can create official skills");
            }
        }
    }

    /**
     * 校验读权限.
     * P2.4.1 / NFR-3.1: personal Skill 仅 owner 可读.
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkReadPermission(String userId, SkillRegistryEntity entity) {
        if ("personal".equals(entity.getTrustTier())) {
            if (!userId.equals(entity.getOwnerId()) && !userId.equals(entity.getUserId())) {
                // P6.2: 检查 RBAC+ABAC 是否授予了 READ 权限
                if (!hasAbacPermission(entity.getId(), userId, MASK_READ)) {
                    throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                        "Cannot access personal skill of another user");
                }
            }
        }
        // team 和 official 级别: 所有已认证用户可读
    }

    /**
     * 校验写权限（更新/状态切换）.
     * P2.4.1~P2.4.3:
     * - personal: 仅 owner
     * - team: owner 或 admin（P2简化版）
     * - official: 仅安全团队
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkWritePermission(String userId, SkillRegistryEntity entity) {
        String trustTier = entity.getTrustTier();

        switch (trustTier) {
            case "personal":
                if (!userId.equals(entity.getOwnerId()) && !userId.equals(entity.getUserId())) {
                    // P6.2: 检查 RBAC+ABAC 是否授予了 WRITE 权限
                    if (!hasAbacPermission(entity.getId(), userId, MASK_WRITE)) {
                        throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                            "Only the owner can modify personal skills");
                    }
                }
                break;

            case "official":
                if (!hasPermission(PERM_OFFICIAL_WRITE)) {
                    // P6.2: 检查 RBAC+ABAC 是否授予了 WRITE 权限
                    if (!hasAbacPermission(entity.getId(), userId, MASK_WRITE)) {
                        throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                            "Only security team can modify official skills");
                    }
                }
                break;

            case "team":
                // P2 简化版: owner 或 admin 可写
                if (!userId.equals(entity.getOwnerId()) && !hasPermission(PERM_ADMIN)) {
                    // P6.2: 检查 RBAC+ABAC 是否授予了 WRITE 权限
                    if (!hasAbacPermission(entity.getId(), userId, MASK_WRITE)) {
                        throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                            "Only the owner or admin can modify team skills");
                    }
                }
                break;

            default:
                throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                    "Unknown trust tier: " + trustTier);
        }
    }

    /**
     * 校验删除权限.
     * 与写权限一致。
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkDeletePermission(String userId, SkillRegistryEntity entity) {
        checkWritePermission(userId, entity);
    }

    // ======================== RBAC+ABAC 权限模型（P6.2）========================

    /**
     * 校验执行权限.
     * P6.2.3: 检查用户是否具有 EXECUTE 权限位.
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkExecutePermission(String userId, SkillRegistryEntity entity) {
        // owner 默认具有执行权限
        if (userId.equals(entity.getOwnerId()) || userId.equals(entity.getUserId())) {
            return;
        }

        // official Skill 所有已认证用户可执行
        if ("official".equals(entity.getTrustTier())) {
            return;
        }

        // P6.2: 检查 RBAC+ABAC 是否授予了 EXECUTE 权限
        if (!hasAbacPermission(entity.getId(), userId, MASK_EXECUTE)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "No execute permission for skill: " + entity.getSkillCode());
        }
    }

    /**
     * 校验管理权限.
     * P6.2.3: 检查用户是否具有 MANAGE 权限位.
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkManagePermission(String userId, SkillRegistryEntity entity) {
        // owner 默认具有管理权限
        if (userId.equals(entity.getOwnerId()) || userId.equals(entity.getUserId())) {
            return;
        }

        // P6.2: 检查 RBAC+ABAC 是否授予了 MANAGE 权限
        if (!hasAbacPermission(entity.getId(), userId, MASK_MANAGE)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "No manage permission for skill: " + entity.getSkillCode());
        }
    }

    /**
     * 校验审计权限.
     * P6.2.3: 检查用户是否具有 AUDIT 权限位.
     *
     * @param userId 当前用户ID
     * @param entity Skill 实体
     */
    public void checkAuditPermission(String userId, SkillRegistryEntity entity) {
        // owner 默认具有审计权限
        if (userId.equals(entity.getOwnerId()) || userId.equals(entity.getUserId())) {
            return;
        }

        // 具备 skill:admin 权限的用户可审计
        if (hasPermission(PERM_ADMIN)) {
            return;
        }

        // P6.2: 检查 RBAC+ABAC 是否授予了 AUDIT 权限
        if (!hasAbacPermission(entity.getId(), userId, MASK_AUDIT)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                "No audit permission for skill: " + entity.getSkillCode());
        }
    }

    /**
     * 检查用户是否具有指定的 RBAC+ABAC 权限位.
     *
     * <p>四级主体聚合校验（按优先级合并）：
     * <ol>
     *   <li>user: 直接匹配 userId</li>
     *   <li>role: 匹配用户所属角色（V1 简化：从 UserContext.permissions 解析 role: 前缀）</li>
     *   <li>team: 匹配用户所属团队（V1 简化：从 UserContext.permissions 解析 team: 前缀）</li>
     *   <li>tenant: 匹配用户所属租户（UserContext.tenantId）</li>
     * </ol>
     *
     * @param skillId Skill ID
     * @param userId  用户ID
     * @param mask    权限位掩码（MASK_READ/WRITE/EXECUTE/MANAGE/AUDIT）
     * @return true 表示具有指定权限
     */
    public boolean hasAbacPermission(Long skillId, String userId, int mask) {
        try {
            // 1. user 主体校验
            if ((getPermissionMask(skillId, "user", userId) & mask) != 0) {
                return true;
            }

            // 2. role 主体校验（V1 简化：从 permissions 解析 role:xxx）
            List<String> permissions = UserContext.getPermissions();
            if (permissions != null) {
                for (String perm : permissions) {
                    if (perm != null && perm.startsWith("role:")) {
                        String roleId = perm.substring(5);
                        if ((getPermissionMask(skillId, "role", roleId) & mask) != 0) {
                            return true;
                        }
                    }
                }

                // 3. team 主体校验（V1 简化：从 permissions 解析 team:xxx）
                for (String perm : permissions) {
                    if (perm != null && perm.startsWith("team:")) {
                        String teamId = perm.substring(5);
                        if ((getPermissionMask(skillId, "team", teamId) & mask) != 0) {
                            return true;
                        }
                    }
                }
            }

            // 4. tenant 主体校验
            String tenantId = UserContext.getTenantId();
            if (tenantId != null && !tenantId.isBlank()) {
                if ((getPermissionMask(skillId, "tenant", tenantId) & mask) != 0) {
                    return true;
                }
            }
        } catch (Exception e) {
            log.warn("SkillPermissionChecker: ABAC check failed skillId={} userId={} mask={} error={}",
                    skillId, userId, mask, e.getMessage());
        }

        return false;
    }

    /**
     * 查询指定主体对 Skill 的权限位掩码（直接访问 Repository，避免循环依赖）.
     *
     * @param skillId     Skill ID
     * @param subjectType 主体类型
     * @param subjectId   主体ID
     * @return 权限位掩码（无配置返回 0）
     */
    private int getPermissionMask(Long skillId, String subjectType, String subjectId) {
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
     * 从 UserContext 获取当前用户权限列表，检查是否包含指定权限.
     */
    private boolean hasPermission(String permission) {
        List<String> permissions = UserContext.getPermissions();
        return permissions != null && permissions.contains(permission);
    }
}
