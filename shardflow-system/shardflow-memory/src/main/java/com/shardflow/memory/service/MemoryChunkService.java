package com.shardflow.memory.service;

import com.shardflow.common.dto.memory.MemoryCreateRequest;
import com.shardflow.common.dto.memory.MemoryCreateResponse;
import com.shardflow.common.dto.memory.MemorySearchRequest;
import com.shardflow.common.dto.memory.MemorySearchResponse;
import com.shardflow.common.dto.memory.MemoryUpdateResponse;
import com.shardflow.common.entity.MemoryChunkEntity;

import java.util.Map;
import java.util.Optional;

/**
 * Memory chunk service interface.
 * Provides CRUD operations, conflict detection, and search for memory chunks.
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
}
