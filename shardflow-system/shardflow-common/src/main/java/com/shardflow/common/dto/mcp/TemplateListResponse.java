package com.shardflow.common.dto.mcp;

import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

/**
 * 模板列表响应 DTO.
 * Per spec section 5.4: GET /api/v1/mcp/templates
 */
@Data
@NoArgsConstructor
public class TemplateListResponse {

    private List<TemplateSummary> templates;

    private Long total;

    private String category;

    @Data
    @NoArgsConstructor
    public static class TemplateSummary {
        private String templateId;
        private String displayName;
        private String category;
        private String description;
        private String iconUrl;
        private String transport;
        private String authType;
        private List<String> tags;
    }
}
