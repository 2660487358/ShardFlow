package com.shardflow.mcp.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.repository.McpToolRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.time.Instant;
import java.util.*;

@Service
public class McpToolService {
    private static final Logger log = LoggerFactory.getLogger(McpToolService.class);
    private final McpToolRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    private final Map<String, Integer> failureCounters = new HashMap<>();

    public McpToolService(McpToolRepository repository,
                          RedisTemplate<String, Object> redisTemplate,
                          ObjectMapper objectMapper) {
        this.repository = repository;
        this.redisTemplate = redisTemplate;
        this.objectMapper = objectMapper;
    }

    public List<McpToolEntity> listTools(String status) {
        if (status != null && !status.isBlank()) {
            return repository.findByStatus(status.toUpperCase());
        }
        return repository.findAll();
    }

    public Optional<McpToolEntity> getTool(String toolId) {
        return repository.findById(toolId);
    }

    @Transactional
    public McpToolEntity registerTool(McpToolEntity tool) {
        if (tool.getToolId() == null || tool.getToolId().isBlank()) {
            tool.setToolId("mcp-" + tool.getToolName().replaceAll("[^a-zA-Z0-9]", "-").toLowerCase());
        }
        tool.setStatus("ACTIVE");
        return repository.save(tool);
    }

    @Transactional
    public Optional<McpToolEntity> updateTool(String toolId, McpToolEntity updates) {
        return repository.findById(toolId).map(existing -> {
            if (updates.getToolName() != null) existing.setToolName(updates.getToolName());
            if (updates.getDescription() != null) existing.setDescription(updates.getDescription());
            if (updates.getMcpServerUrl() != null) existing.setMcpServerUrl(updates.getMcpServerUrl());
            if (updates.getInputSchema() != null) existing.setInputSchema(updates.getInputSchema());
            if (updates.getOutputSchema() != null) existing.setOutputSchema(updates.getOutputSchema());
            if (updates.getPermissions() != null) existing.setPermissions(updates.getPermissions());
            if (updates.getVersion() != null) existing.setVersion(updates.getVersion());
            return repository.save(existing);
        });
    }

    @Transactional
    public boolean deleteTool(String toolId) {
        return repository.findById(toolId).map(tool -> {
            tool.setStatus("INACTIVE");
            repository.save(tool);
            return true;
        }).orElse(false);
    }

    public List<Map<String, Object>> healthCheck() {
        List<McpToolEntity> tools = repository.findByStatus("ACTIVE");
        List<Map<String, Object>> results = new ArrayList<>();
        for (McpToolEntity tool : tools) {
            Map<String, Object> result = new HashMap<>();
            result.put("tool_name", tool.getToolName());
            try {
                long start = System.currentTimeMillis();
                HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(tool.getMcpServerUrl() + "/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                long latency = System.currentTimeMillis() - start;
                result.put("healthy", response.statusCode() == 200);
                result.put("latency_ms", latency);
            } catch (Exception e) {
                result.put("healthy", false);
                result.put("error", e.getMessage());
            }
            results.add(result);
        }
        return results;
    }

    @Scheduled(fixedRate = 300000)
    public void scheduledHealthCheck() {
        List<McpToolEntity> tools = repository.findByStatus("ACTIVE");
        for (McpToolEntity tool : tools) {
            try {
                HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(tool.getMcpServerUrl() + "/health"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() == 200) {
                    failureCounters.remove(tool.getToolId());
                    if ("ERROR".equals(tool.getStatus())) {
                        updateToolStatus(tool, "ACTIVE");
                    }
                } else {
                    recordFailure(tool);
                }
            } catch (Exception e) {
                recordFailure(tool);
            }
            tool.setLastHealthCheck(Instant.now());
            repository.save(tool);
        }
    }

    private void recordFailure(McpToolEntity tool) {
        int count = failureCounters.merge(tool.getToolId(), 1, Integer::sum);
        if (count >= 3) {
            updateToolStatus(tool, "ERROR");
        }
    }

    private void updateToolStatus(McpToolEntity tool, String newStatus) {
        String oldStatus = tool.getStatus();
        tool.setStatus(newStatus);
        repository.save(tool);
        try {
            String payload = objectMapper.writeValueAsString(Map.of(
                "tool_id", tool.getToolId(),
                "tool_name", tool.getToolName(),
                "old_status", oldStatus,
                "new_status", newStatus
            ));
            redisTemplate.convertAndSend("shardflow:" + tool.getToolId() + ":events", payload);
        } catch (JsonProcessingException e) {
            log.warn("Failed to publish MCP status event", e);
        }
    }
}
