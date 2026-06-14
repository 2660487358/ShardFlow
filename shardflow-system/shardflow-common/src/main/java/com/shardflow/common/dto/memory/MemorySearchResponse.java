package com.shardflow.common.dto.memory;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Response DTO for memory search results.
 * Per spec section 7.2: Response 200 OK
 */
@Data
@NoArgsConstructor
public class MemorySearchResponse {

    private List<MemoryResultItem> results;

    private Integer total;

    private Long searchTimeMs;

    @Data
    @NoArgsConstructor
    public static class MemoryResultItem {
        private String memoryId;
        private String content;
        private Double similarityScore;
        private Double confidence;
        private String category;
        private Map<String, Object> metadata;
    }
}
