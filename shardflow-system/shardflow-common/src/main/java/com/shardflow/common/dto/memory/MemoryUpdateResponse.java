package com.shardflow.common.dto.memory;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.Map;

/**
 * Response DTO for memory update.
 * Per spec section 7.4: Response 200 OK
 */
@Data
@NoArgsConstructor
public class MemoryUpdateResponse {

    private String memoryId;

    private String status;

    private Integer version;

    private Instant updatedAt;
}
