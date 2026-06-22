package com.shardflow.config.service;

import com.shardflow.common.config.SkillRedisConstants;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Component;

import java.util.concurrent.TimeUnit;

/**
 * Skill 缓存失效策略组件.
 *
 * <p>Per Skills管理需求规格文档 FR-9 / 实施计划 P1.3.2.
 * <p>在以下场景主动失效 Redis 缓存：
 * <ul>
 *   <li>Skill 状态变更（draft→published 等）→ 失效 meta + list</li>
 *   <li>Skill 元数据更新（名称/描述/schema 等）→ 失效 meta + list</li>
 *   <li>Skill 删除 → 失效 meta + list</li>
 *   <li>版本发布/回滚 → 失效 meta + list（current_version 变更）</li>
 *   <li>Agent-Skill 绑定变更 → 失效 index + list</li>
 *   <li>权限变更 → 失效 meta + list（可见性可能变化）</li>
 * </ul>
 *
 * <p>降级策略：Redis 不可用时仅记录日志，不阻断主流程（缓存失效失败不影响数据一致性，
 * 缓存 TTL 5 分钟后自然过期）。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SkillCacheEvictor {

    private final RedisTemplate<String, Object> redisTemplate;

    /**
     * 失效单个 Skill 元数据缓存.
     */
    public void evictSkillMeta(String userId, String skillCode) {
        try {
            redisTemplate.delete(SkillRedisConstants.skillMetaKey(userId, skillCode));
            log.debug("Evicted skill meta cache: userId={}, skillCode={}", userId, skillCode);
        } catch (Exception e) {
            log.warn("Failed to evict skill meta cache (userId={}, skillCode={}): {}", userId, skillCode, e.getMessage());
        }
    }

    /**
     * 失效 Agent 挂载索引缓存.
     */
    public void evictSkillIndex(String userId, String agentId) {
        try {
            redisTemplate.delete(SkillRedisConstants.skillIndexKey(userId, agentId));
            log.debug("Evicted skill index cache: userId={}, agentId={}", userId, agentId);
        } catch (Exception e) {
            log.warn("Failed to evict skill index cache (userId={}, agentId={}): {}", userId, agentId, e.getMessage());
        }
    }

    /**
     * 失效用户 Skill 列表缓存.
     */
    public void evictSkillList(String userId) {
        try {
            redisTemplate.delete(SkillRedisConstants.skillListKey(userId));
            log.debug("Evicted skill list cache: userId={}", userId);
        } catch (Exception e) {
            log.warn("Failed to evict skill list cache (userId={}): {}", userId, e.getMessage());
        }
    }

    /**
     * 失效分类列表缓存.
     */
    public void evictCategories(String userId) {
        try {
            redisTemplate.delete(SkillRedisConstants.skillCategoriesKey(userId));
            log.debug("Evicted skill categories cache: userId={}", userId);
        } catch (Exception e) {
            log.warn("Failed to evict skill categories cache (userId={}): {}", userId, e.getMessage());
        }
    }

    /**
     * Skill 变更（创建/更新/删除/状态切换）时失效相关缓存.
     * 失效范围：meta + list。
     */
    public void evictOnSkillChange(String userId, String skillCode) {
        evictSkillMeta(userId, skillCode);
        evictSkillList(userId);
    }

    /**
     * 版本发布/回滚时失效相关缓存.
     * 失效范围：meta + list（current_version 变更影响列表与详情）。
     */
    public void evictOnVersionPublish(String userId, String skillCode) {
        evictSkillMeta(userId, skillCode);
        evictSkillList(userId);
    }

    /**
     * Agent-Skill 绑定变更时失效相关缓存.
     * 失效范围：index + list。
     */
    public void evictOnBindingChange(String userId, String agentId) {
        evictSkillIndex(userId, agentId);
        evictSkillList(userId);
    }

    /**
     * Agent-Skill 绑定变更时失效相关缓存（含 Skill 维度）.
     * 失效范围：meta + index + list。
     */
    public void evictOnBindingChange(String userId, String skillCode, String agentId) {
        evictSkillMeta(userId, skillCode);
        evictSkillIndex(userId, agentId);
        evictSkillList(userId);
    }

    /**
     * 权限变更时失效相关缓存.
     * 失效范围：meta + list（可见性可能变化）。
     */
    public void evictOnPermissionChange(String userId, String skillCode) {
        evictSkillMeta(userId, skillCode);
        evictSkillList(userId);
    }

    /**
     * 写入 Skill 元数据缓存（带 TTL）.
     * 供 SkillService 读取时回填缓存使用。
     */
    public void cacheSkillMeta(String userId, String skillCode, String json) {
        try {
            redisTemplate.opsForValue().set(
                SkillRedisConstants.skillMetaKey(userId, skillCode),
                json,
                SkillRedisConstants.SKILL_META_TTL_SECONDS,
                TimeUnit.SECONDS
            );
        } catch (Exception e) {
            log.warn("Failed to cache skill meta (userId={}, skillCode={}): {}", userId, skillCode, e.getMessage());
        }
    }

    /**
     * 读取 Skill 元数据缓存.
     * @return 缓存 JSON，未命中返回 null
     */
    public String readSkillMeta(String userId, String skillCode) {
        try {
            Object value = redisTemplate.opsForValue().get(SkillRedisConstants.skillMetaKey(userId, skillCode));
            return value == null ? null : value.toString();
        } catch (Exception e) {
            log.warn("Failed to read skill meta cache (userId={}, skillCode={}): {}", userId, skillCode, e.getMessage());
            return null;
        }
    }
}
