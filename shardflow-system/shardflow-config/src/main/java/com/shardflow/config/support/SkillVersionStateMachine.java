package com.shardflow.config.support;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;
import java.util.Set;

/**
 * Skill 版本状态流转校验器.
 *
 * <p>Per Skills管理需求规格文档 DR-3 / 实施计划 P3.1.5.
 * <p>合法版本状态流转：
 * <pre>
 *     draft        → staging
 *     staging      → production
 *     staging      → draft（回退到草稿）
 *     production   → rolled_back（回滚）
 *     rolled_back  →（终态，不可再变更）
 * </pre>
 */
@Slf4j
public final class SkillVersionStateMachine {

    private SkillVersionStateMachine() {}

    private static final Map<String, Set<String>> ALLOWED_TRANSITIONS = Map.of(
        "draft",       Set.of("staging"),
        "staging",     Set.of("production", "draft"),
        "production",  Set.of("rolled_back"),
        "rolled_back", Set.of()
    );

    /**
     * 检查版本状态流转是否合法.
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
     * 校验版本状态流转，非法流转抛出 400 异常.
     *
     * @param current 当前状态
     * @param target  目标状态
     * @throws ResponseStatusException 如果状态流转非法
     */
    public static void checkTransition(String current, String target) {
        if (!isTransitionAllowed(current, target)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid skill version status transition: " + current + " -> " + target);
        }
    }
}
