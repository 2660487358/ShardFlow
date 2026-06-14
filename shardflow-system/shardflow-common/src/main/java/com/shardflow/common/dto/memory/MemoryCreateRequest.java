package com.shardflow.common.dto.memory;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Map;

/**
 * Request DTO for creating a new memory chunk.
 * Per spec section 7.1: POST /api/v1/memory
 */
@Data
@NoArgsConstructor
public class MemoryCreateRequest {

    private String userId;

    private String memoryType; // semantic | episodic

    private String category;   // preference|profile|history|decision|strategy

    private ContentPayload content;

    private Double confidence;

    private String source;     // conversation|explicit_confirmation|ner_extraction|scheduled_task

    private String sessionId;

    private Map<String, Object> metadata;

    @Data
    @NoArgsConstructor
    public static class ContentPayload {
        private String text;
        private Map<String, Object> structured;
    }
}
