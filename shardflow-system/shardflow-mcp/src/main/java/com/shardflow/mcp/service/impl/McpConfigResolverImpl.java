package com.shardflow.mcp.service.impl;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.dto.mcp.QuickConfigRequest;
import com.shardflow.common.dto.mcp.ToolRegisterRequest;
import com.shardflow.common.dto.mcp.ToolRegisterResponse;
import com.shardflow.common.entity.McpQuickTemplateEntity;
import com.shardflow.mcp.service.McpConfigResolver;
import com.shardflow.mcp.service.McpToolService;
import com.shardflow.mcp.service.TemplateRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class McpConfigResolverImpl implements McpConfigResolver {

    private final TemplateRegistry templateRegistry;
    private final McpToolService toolService;
    private final ObjectMapper objectMapper;

    @Override
    public ToolRegisterResponse resolveAndRegister(QuickConfigRequest request) {
        McpQuickTemplateEntity template = templateRegistry.getById(request.getTemplate())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Template not found: " + request.getTemplate()
            ));

        ToolRegisterRequest fullRequest = buildFullRequest(request, template);

        return toolService.registerTool(fullRequest);
    }

    private ToolRegisterRequest buildFullRequest(QuickConfigRequest quick, McpQuickTemplateEntity template) {
        ToolRegisterRequest full = new ToolRegisterRequest();

        full.setToolName(quick.getName());
        full.setDescription(template.getDescription());
        full.setCategory(template.getCategory());
        full.setTransport(quick.getTransport());

        full.setMcpServerUrl(buildServerUrl(quick.getTransport(), quick.getConnection()));

        full.setInputSchema(parseJsonMap(template.getInputSchema()));
        full.setOutputSchema(parseJsonMap(template.getOutputSchema()));

        full.setVersion("1.0.0");
        full.setTimeoutSeconds(quick.getTimeoutSeconds() != null ? quick.getTimeoutSeconds() : 30);
        full.setRetryCount(quick.getRetryCount() != null ? quick.getRetryCount() : 1);

        if (template.getTags() != null) {
            full.setTags(parseJsonList(template.getTags()));
        }

        full.setAuthConfig(buildAuthConfig(template.getAuthType(), quick.getEnv()));

        return full;
    }

    private String buildServerUrl(String transport, Map<String, Object> connection) {
        if (connection == null) {
            return null;
        }

        switch (transport) {
            case "stdio":
                String command = (String) connection.get("command");
                return command != null ? command : "";

            case "sse":
            case "cloud":
                String url = (String) connection.get("url");
                return url != null ? url : "";

            default:
                log.warn("Unknown transport type: {}", transport);
                return "";
        }
    }

    private ToolRegisterRequest.AuthConfig buildAuthConfig(String authType, Map<String, String> env) {
        if (authType == null || "none".equals(authType)) {
            return null;
        }

        ToolRegisterRequest.AuthConfig config = new ToolRegisterRequest.AuthConfig();
        config.setType(authType);

        if (env == null || env.isEmpty()) {
            return config;
        }

        switch (authType) {
            case "bearer":
                if (env.containsKey("API_KEY")) {
                    config.setTokenKey("API_KEY");
                    config.setKeyValueEnv("API_KEY");
                }
                break;

            case "basic":
                if (env.containsKey("USERNAME") && env.containsKey("PASSWORD")) {
                    config.setKeyName("USERNAME");
                    config.setKeyValueEnv("PASSWORD");
                }
                break;

            case "oauth2":
                if (env.containsKey("CLIENT_ID") && env.containsKey("CLIENT_SECRET")) {
                    config.setClientIdEnv("CLIENT_ID");
                    config.setClientSecretEnv("CLIENT_SECRET");
                }
                break;

            default:
                log.warn("Unknown auth type: {}", authType);
        }

        return config;
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

    private java.util.List<String> parseJsonList(String json) {
        if (json == null || json.isEmpty()) {
            return java.util.Collections.emptyList();
        }

        try {
            return objectMapper.readValue(json, new TypeReference<java.util.List<String>>() {});
        } catch (Exception e) {
            log.error("Failed to parse JSON list: {}", json, e);
            return java.util.Collections.emptyList();
        }
    }
}
