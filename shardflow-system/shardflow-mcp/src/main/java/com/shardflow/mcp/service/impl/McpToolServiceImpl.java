package com.shardflow.mcp.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.repository.McpToolRepository;
import com.shardflow.mcp.service.McpToolService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
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

@Slf4j
@Service
@RequiredArgsConstructor
public class McpToolServiceImpl implements McpToolService {

    private final McpToolRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final Map<String, Integer> failureCounters = new HashMap<>();
    private final HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();

    @Override
    public List<McpToolEntity> listTools(String status) {
        if (status != null && !status.isBlank()) {
            return repository.selectList(
                new LambdaQueryWrapper<McpToolEntity>()
                    .eq(McpToolEntity::getStatus, status.toUpperCase())
            );
        }
        return repository.selectList(null);
    }

    @Override
    public Optional<McpToolEntity> getTool(String toolId) {
        return Optional.ofNullable(repository.selectById(toolId));
    }

    @Override
    @Transactional
    public McpToolEntity registerTool(McpToolEntity tool) {
        if (tool.getToolId() == null || tool.getToolId().isBlank()) {
            tool.setToolId("mcp-" + tool.getToolName().replaceAll("[^a-zA-Z0-9]", "-").toLowerCase());
        }
        tool.setStatus("ACTIVE");
        repository.insert(tool);
        return tool;
    }

    @Override
    @Transactional
    public Optional<McpToolEntity> updateTool(String toolId, McpToolEntity updates) {
        McpToolEntity existing = repository.selectById(toolId);
        if (existing == null) return Optional.empty();
        if (updates.getToolName() != null) existing.setToolName(updates.getToolName());
        if (updates.getDescription() != null) existing.setDescription(updates.getDescription());
        if (updates.getMcpServerUrl() != null) existing.setMcpServerUrl(updates.getMcpServerUrl());
        if (updates.getInputSchema() != null) existing.setInputSchema(updates.getInputSchema());
        if (updates.getOutputSchema() != null) existing.setOutputSchema(updates.getOutputSchema());
        if (updates.getPermissions() != null) existing.setPermissions(updates.getPermissions());
        if (updates.getVersion() != null) existing.setVersion(updates.getVersion());
        repository.updateById(existing);
        return Optional.of(existing);
    }

    @Override
    @Transactional
    public boolean deleteTool(String toolId) {
        McpToolEntity tool = repository.selectById(toolId);
        if (tool == null) return false;
        tool.setStatus("INACTIVE");
        repository.updateById(tool);
        return true;
    }

    @Override
    public List<Map<String, Object>> healthCheck() {
        List<McpToolEntity> tools = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>().eq(McpToolEntity::getStatus, "ACTIVE")
        );
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
        List<McpToolEntity> tools = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>().eq(McpToolEntity::getStatus, "ACTIVE")
        );
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
            repository.updateById(tool);
        }
    }

    private void recordFailure(McpToolEntity tool) {
        int count = failureCounters.merge(tool.getToolId(), 1, Integer::sum);
        if (count >= 3) {
            updateToolStatus(tool, "ERROR");
        }
    }

    private void updateToolStatus(McpToolEntity tool, String newStatus) {
        tool.setStatus(newStatus);
        repository.updateById(tool);
        try {
            String payload = objectMapper.writeValueAsString(Map.of(
                "tool_id", tool.getToolId(),
                "tool_name", tool.getToolName(),
                "old_status", tool.getStatus(),
                "new_status", newStatus
            ));
            redisTemplate.convertAndSend("shardflow:" + tool.getToolId() + ":events", payload);
        } catch (JsonProcessingException e) {
            log.warn("Failed to publish MCP status event", e);
        }
    }
}
