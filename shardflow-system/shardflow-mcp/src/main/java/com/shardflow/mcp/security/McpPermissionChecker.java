package com.shardflow.mcp.security;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.McpToolEntity;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * MCP 工具调用权限校验器 (SEC-AUTH-003).
 *
 * <p>校验用户是否有该工具的访问权限。
 * 权限定义在工具的 permissions 字段中，为字符串列表。
 * 如果工具未定义 permissions，则默认允许访问。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McpPermissionChecker {

    private final ObjectMapper objectMapper;

    /**
     * 校验用户是否有该工具的访问权限.
     *
     * @param entity          工具实体
     * @param userPermissions 用户拥有的权限列表
     * @return true 表示有权限，false 表示无权限
     */
    public boolean checkPermission(McpToolEntity entity, List<String> userPermissions) {
        List<String> toolPermissions = parsePermissions(entity.getPermissions());
        if (toolPermissions == null || toolPermissions.isEmpty()) {
            return true; // 无需特殊权限
        }
        if (userPermissions == null || userPermissions.isEmpty()) {
            log.warn("Permission denied: tool={} requires {} but user has no permissions",
                entity.getToolName(), toolPermissions);
            return false;
        }
        for (String required : toolPermissions) {
            if (userPermissions.contains(required)) {
                return true;
            }
        }
        log.warn("Permission denied: tool={} requires {}, user has {}",
            entity.getToolName(), toolPermissions, userPermissions);
        return false;
    }

    /**
     * SEC-AUTH-003: 校验用户是否拥有指定的操作权限.
     *
     * @param userId              用户ID
     * @param requiredPermissions 用户需要拥有的权限列表
     * @return true 表示有权限，false 表示无权限
     */
    public boolean checkPermission(String userId, List<String> requiredPermissions) {
        if (requiredPermissions == null || requiredPermissions.isEmpty()) {
            return true;
        }
        List<String> userPermissions = getUserPermissions(userId);
        if (userPermissions == null || userPermissions.isEmpty()) {
            log.warn("Permission denied: user={} has no permissions, requires {}", userId, requiredPermissions);
            return false;
        }
        for (String required : requiredPermissions) {
            if (!userPermissions.contains(required)) {
                log.warn("Permission denied: user={} lacks permission {}", userId, required);
                return false;
            }
        }
        return true;
    }

    /**
     * 获取用户权限列表.
     * TODO: 对接实际权限系统，当前从 UserContext 获取
     */
    private List<String> getUserPermissions(String userId) {
        // 当前从 UserContext 获取，后续对接权限系统
        return com.shardflow.usercontext.context.UserContext.getPermissions();
    }

    /**
     * 校验工具是否为高风险工具 (SEC-TOOL-001).
     */
    public boolean isHighRisk(McpToolEntity entity) {
        return "high".equalsIgnoreCase(entity.getRiskLevel());
    }

    /**
     * 校验工具是否有写操作副作用 (SEC-TOOL-002).
     * 通过 permissions 字段中包含 write/send/create/delete 等关键词判断。
     */
    public boolean hasSideEffects(McpToolEntity entity) {
        List<String> permissions = parsePermissions(entity.getPermissions());
        if (permissions == null) return false;
        return permissions.stream().anyMatch(p ->
            p.contains(":write") || p.contains(":send") ||
            p.contains(":create") || p.contains(":delete")
        );
    }

    private List<String> parsePermissions(String permissionsJson) {
        if (permissionsJson == null || permissionsJson.isBlank()) return null;
        try {
            return objectMapper.readValue(permissionsJson, new TypeReference<List<String>>() {});
        } catch (Exception e) {
            log.warn("Failed to parse permissions JSON: {}", permissionsJson);
            return null;
        }
    }
}
