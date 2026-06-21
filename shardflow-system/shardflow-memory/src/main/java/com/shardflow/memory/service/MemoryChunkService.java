package com.shardflow.memory.service;

import com.shardflow.common.dto.memory.MemoryCreateRequest;
import com.shardflow.common.dto.memory.MemoryCreateResponse;
import com.shardflow.common.dto.memory.MemorySearchRequest;
import com.shardflow.common.dto.memory.MemorySearchResponse;
import com.shardflow.common.dto.memory.MemoryUpdateResponse;
import com.shardflow.common.entity.MemoryChunkEntity;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Memory chunk service interface.
 * Provides CRUD operations, conflict detection, conflict resolution, and search for memory chunks.
 * <p>
 * 规则条款：C-3.3（记忆 CRUD）、C-4.20（幂等）、FIX-KEY-1（Redis Key 4段格式）、C-8.5（禁用 KEYS）。
 */
public interface MemoryChunkService {

    /**
     * Create a new memory chunk with conflict detection.
     */
    MemoryCreateResponse createMemory(MemoryCreateRequest request);

    /**
     * Get a memory chunk by its ID.
     */
    Optional<MemoryChunkEntity> getMemory(String chunkId);

    /**
     * Update an existing memory chunk with version increment.
     */
    MemoryUpdateResponse updateMemory(String chunkId, MemoryCreateRequest request);

    /**
     * Soft-delete a memory chunk.
     */
    boolean deleteMemory(String chunkId);

    /**
     * Search memory chunks (structured query; vector search will be added in P5).
     */
    MemorySearchResponse searchMemory(MemorySearchRequest request);

    /**
     * Export all non-deleted memory chunks for a user.
     */
    Map<String, Object> exportMemory(String userId);

    /**
     * Save memory from callback (Python推理层回调).
     * Parses Map body into MemoryCreateRequest, creates or updates.
     */
    MemoryCreateResponse saveFromCallback(Map<String, Object> body);

    /**
     * 列出用户的所有待解决冲突记忆（C-3.3 冲突解决 API）。
     *
     * @param userId 用户ID
     * @return 待解决冲突的记忆列表
     */
    List<MemoryChunkEntity> listPendingConflicts(String userId);

    /**
     * 解决记忆冲突（C-3.3 冲突解决 API）。
     * <p>
     * 支持三种解决策略：
     * <ul>
     *   <li>KEEP_NEW: 保留新内容，标记冲突已解决</li>
     *   <li>KEEP_OLD: 保留旧内容，标记冲突已解决</li>
     *   <li>MERGE: 合并内容（需提供 resolvedContent）</li>
     * </ul>
     *
     * @param chunkId          记忆块ID
     * @param resolution       解决策略：KEEP_NEW / KEEP_OLD / MERGE
     * @param resolvedContent  合并后的内容（仅 MERGE 策略需要）
     * @return 更新后的记忆实体
     */
    Optional<MemoryChunkEntity> resolveConflict(String chunkId, String resolution, String resolvedContent);
}
