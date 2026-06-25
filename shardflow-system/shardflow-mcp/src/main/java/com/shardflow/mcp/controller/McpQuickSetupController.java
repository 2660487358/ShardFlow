package com.shardflow.mcp.controller;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.mcp.QuickConfigRequest;
import com.shardflow.common.dto.mcp.QuickConfigResponse;
import com.shardflow.common.dto.mcp.TemplateListResponse;
import com.shardflow.common.entity.McpQuickTemplateEntity;
import com.shardflow.mcp.service.McpConfigResolver;
import com.shardflow.mcp.service.TemplateRegistry;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * MCP 快速配置 Controller.
 * 基路径: /api/v1/mcp
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/mcp")
@RequiredArgsConstructor
public class McpQuickSetupController {

    private final McpConfigResolver configResolver;
    private final TemplateRegistry templateRegistry;
    private final ObjectMapper objectMapper;

    /**
     * 快速配置注册.
     * POST /api/v1/mcp/quick-setup
     */
    @PostMapping("/quick-setup")
    @ResponseStatus(HttpStatus.CREATED)
    public Result<QuickConfigResponse> quickSetup(@Valid @RequestBody QuickConfigRequest request) {
        var response = configResolver.resolveAndRegister(request);

        QuickConfigResponse quickResponse = new QuickConfigResponse();
        quickResponse.setToolId(response.getToolId());
        quickResponse.setToolName(response.getToolName());
        quickResponse.setTemplate(request.getTemplate());
        quickResponse.setStatus(response.getStatus());
        quickResponse.setCreatedAt(response.getCreatedAt());

        if (request.getEnv() != null) {
            Map<String, String> masked = new HashMap<>();
            for (String key : request.getEnv().keySet()) {
                masked.put(key, "****");
            }
            quickResponse.setEnvMasked(masked);
        }

        log.info("Quick setup completed: toolId={}, template={}",
            response.getToolId(), request.getTemplate());

        return Result.ok(quickResponse);
    }

    /**
     * 查询模板列表.
     * GET /api/v1/mcp/templates
     */
    @GetMapping("/templates")
    public Result<TemplateListResponse> listTemplates(
            @RequestParam(required = false) String category,
            @RequestParam(required = false) String keyword) {

        List<McpQuickTemplateEntity> templates = templateRegistry.list(category, keyword);

        TemplateListResponse response = new TemplateListResponse();
        response.setTemplates(templates.stream()
            .map(this::toTemplateSummary)
            .collect(Collectors.toList()));
        response.setTotal((long) templates.size());
        response.setCategory(category);

        return Result.ok(response);
    }

    /**
     * 查询模板详情.
     * GET /api/v1/mcp/templates/{templateId}
     */
    @GetMapping("/templates/{templateId}")
    public Result<Map<String, Object>> getTemplateDetail(@PathVariable String templateId) {
        McpQuickTemplateEntity template = templateRegistry.getById(templateId)
            .orElse(null);

        if (template == null) {
            return Result.fail(404, "Template not found: " + templateId);
        }

        Map<String, Object> detail = new HashMap<>();
        detail.put("templateId", template.getTemplateId());
        detail.put("displayName", template.getDisplayName());
        detail.put("category", template.getCategory());
        detail.put("description", template.getDescription());
        detail.put("iconUrl", template.getIconUrl());
        detail.put("transport", template.getTransport());
        detail.put("authType", template.getAuthType());
        detail.put("inputSchema", parseJsonMap(template.getInputSchema()));
        detail.put("outputSchema", parseJsonMap(template.getOutputSchema()));
        detail.put("defaultConnection", parseJsonMap(template.getDefaultConnection()));
        detail.put("defaultEnvVars", parseJsonMap(template.getDefaultEnvVars()));
        detail.put("envVarDescriptions", parseJsonMap(template.getEnvVarDescriptions()));
        detail.put("tags", parseJsonList(template.getTags()));
        detail.put("sortOrder", template.getSortOrder());

        return Result.ok(detail);
    }

    private TemplateListResponse.TemplateSummary toTemplateSummary(McpQuickTemplateEntity entity) {
        TemplateListResponse.TemplateSummary summary = new TemplateListResponse.TemplateSummary();
        summary.setTemplateId(entity.getTemplateId());
        summary.setDisplayName(entity.getDisplayName());
        summary.setCategory(entity.getCategory());
        summary.setDescription(entity.getDescription());
        summary.setIconUrl(entity.getIconUrl());
        summary.setTransport(entity.getTransport());
        summary.setAuthType(entity.getAuthType());
        summary.setTags(parseJsonList(entity.getTags()));
        return summary;
    }

    private Map<String, Object> parseJsonMap(String json) {
        if (json == null || json.isEmpty()) {
            return new HashMap<>();
        }

        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            log.error("Failed to parse JSON map: {}", json, e);
            return new HashMap<>();
        }
    }

    private List<String> parseJsonList(String json) {
        if (json == null || json.isEmpty()) {
            return List.of();
        }

        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {});
        } catch (Exception e) {
            log.error("Failed to parse JSON list: {}", json, e);
            return List.of();
        }
    }
}
