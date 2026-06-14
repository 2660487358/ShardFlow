package com.shardflow.common.dto.memory;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Request DTO for memory search.
 * Per spec section 7.2: POST /api/v1/memory/search
 */
@Data
@NoArgsConstructor
public class MemorySearchRequest {

    private String userId;

    private String query;

    private String searchType; // hybrid | vector | structured

    private Integer topK = 10;

    private SearchFilters filters;

    @Data
    @NoArgsConstructor
    public static class SearchFilters {
        private List<String> memoryType;
        private List<String> category;
        private String createdAfter;
        private String createdBefore;
        private Double minConfidence;
    }
}
