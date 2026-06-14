package com.shardflow.mcp.statemachine;

import lombok.extern.slf4j.Slf4j;

import java.util.Map;
import java.util.Set;

/**
 * MCP 工具状态机.
 * 实现 DRAFT / ACTIVE / INACTIVE 三状态流转校验 (FR-STATUS-002).
 *
 * <p>合法流转：
 * <ul>
 *   <li>DRAFT → ACTIVE（激活）</li>
 *   <li>DRAFT → INACTIVE（删除）</li>
 *   <li>ACTIVE → INACTIVE（停用）</li>
 *   <li>INACTIVE → ACTIVE（重新激活）</li>
 * </ul>
 *
 * <p>BUILTIN 类型工具始终为 ACTIVE，不可变更状态 (FR-BUILTIN-003)。
 */
@Slf4j
public final class ToolStateMachine {

    private ToolStateMachine() {}

    private static final Map<String, Set<String>> ALLOWED_TRANSITIONS = Map.of(
        "DRAFT", Set.of("ACTIVE", "INACTIVE"),
        "ACTIVE", Set.of("INACTIVE"),
        "INACTIVE", Set.of("ACTIVE")
    );

    /**
     * 校验状态流转是否合法.
     *
     * @param currentStatus 当前状态
     * @param targetStatus  目标状态
     * @return true 如果流转合法
     */
    public static boolean isTransitionAllowed(String currentStatus, String targetStatus) {
        if (currentStatus == null || targetStatus == null) {
            return false;
        }
        String current = currentStatus.toUpperCase();
        String target = targetStatus.toUpperCase();
        if (current.equals(target)) {
            return false;
        }
        Set<String> allowed = ALLOWED_TRANSITIONS.get(current);
        return allowed != null && allowed.contains(target);
    }

    /**
     * 校验状态流转，非法时抛出异常.
     *
     * @param currentStatus 当前状态
     * @param targetStatus  目标状态
     * @throws IllegalStateException 如果流转非法
     */
    public static void checkTransition(String currentStatus, String targetStatus) {
        if (!isTransitionAllowed(currentStatus, targetStatus)) {
            throw new IllegalStateException(
                "Invalid status transition: " + currentStatus + " → " + targetStatus);
        }
    }

    /**
     * 校验 BUILTIN 工具是否允许状态变更（不允许）.
     *
     * @param toolType 工具类型
     * @throws IllegalStateException 如果 BUILTIN 工具尝试变更状态
     */
    public static void checkBuiltinImmutable(String toolType) {
        if ("BUILTIN".equalsIgnoreCase(toolType)) {
            throw new IllegalStateException(
                "BUILTIN tools cannot change status — they are always ACTIVE");
        }
    }
}
