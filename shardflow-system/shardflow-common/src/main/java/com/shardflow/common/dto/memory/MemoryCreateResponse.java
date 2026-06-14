package com.shardflow.common.dto.memory;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Map;

/**
 * Response DTO for memory creation.
 * Per spec section 7.1: Response 201 Created
 */
@Data
@NoArgsConstructor
public class MemoryCreateResponse {

    private String memoryId;

    private String status;

    private Boolean conflictDetected;

    private Instant createdAt;
}
