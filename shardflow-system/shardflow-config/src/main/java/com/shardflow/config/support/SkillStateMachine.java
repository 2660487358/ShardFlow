package com.shardflow.config.support;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;
import java.util.Set;

/**
 * Skill 状态流转校验器.
 *
 * <p>Per Skills管理需求规格文档 DR-2 / 实施计划 P2.2.6.
 * <p>合法状态流转：
 * <pre>
 *     draft      → reviewing, published, archived
 *     reviewing  → draft, published
 *     published  → deprecated, reviewing
 *     deprecated → published, archived
 *     archived   → (终态，不可再变更)
 * </pre>
 */
@Slf4j
public final class SkillStateMachine {

    private SkillStateMachine() {}

    private static final Map<String, Set<String>> ALLOWED_TRANSITIONS = Map.of(
        "draft",      Set.of("reviewing", "published", "archived"),
        "reviewing",  Set.of("draft", "published"),
        "published",  Set.of("deprecated", "reviewing"),
        "deprecated", Set.of("published", "archived"),
        "archived",   Set.of()
    );

    /**
     * 检查状态流转是否合法.
     *
     * @param current 当前状态
     * @param target  目标状态
     * @return true 如果流转合法
     */
    public static boolean isTransitionAllowed(String current, String target) {
        if (current == null || target == null) return false;
        if (current.equals(target)) return false;
        Set<String> allowed = ALLOWED_TRANSITIONS.get(current);
        return allowed != null && allowed.contains(target);
    }

    /**
     * 校验状态流转，非法流转抛出 400 异常.
     *
     * @param current 当前状态
     * @param target  目标状态
     * @throws ResponseStatusException 如果状态流转非法
     */
    public static void checkTransition(String current, String target) {
        if (!isTransitionAllowed(current, target)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid skill status transition: " + current + " -> " + target);
        }
    }
}
