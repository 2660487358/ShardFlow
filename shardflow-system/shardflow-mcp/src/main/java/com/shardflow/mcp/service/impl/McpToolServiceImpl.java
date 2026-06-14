package com.shardflow.mcp.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.shardflow.common.config.McpRedisConstants;
import com.shardflow.common.dto.mcp.*;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.common.util.AesEncryptionUtil;
import com.shardflow.mcp.health.McpHealthCheckScheduler;
import com.shardflow.mcp.health.McpHealthChecker.HealthCheckResult;
import com.shardflow.mcp.publisher.ToolStatePublisher;
import com.shardflow.mcp.repository.McpToolRepository;
import com.shardflow.mcp.security.McpPermissionChecker;
import com.shardflow.mcp.security.McpTransportSecurity;
import com.shardflow.mcp.service.McpAuditService;
import com.shardflow.mcp.service.McpToolService;
import com.shardflow.mcp.service.McpVersionService;
import com.shardflow.mcp.statemachine.ToolStateMachine;
import com.shardflow.mcp.validator.JsonSchemaValidator;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class McpToolServiceImpl implements McpToolService {

    private final McpToolRepository repository;
    private final RedisTemplate<String, Object> redisTemplate;
    private final ObjectMapper objectMapper;
    private final JsonSchemaValidator jsonSchemaValidator;
    private final ToolStatePublisher toolStatePublisher;
    private final McpHealthCheckScheduler healthCheckScheduler;
    private final McpVersionService versionService;
    private final McpAuditService auditService;
    private final McpPermissionChecker permissionChecker;
    private final McpTransportSecurity transportSecurity;

    // ======================== P2.2 工具注册 ========================

    @Override
    @Transactional
    public ToolRegisterResponse registerTool(ToolRegisterRequest request) {
        String userId = UserContext.getUserId();

        // SEC-AUTH-003: 校验用户是否有注册工具的权限
        checkPermission(userId, List.of("mcp:tool:register"));

        // FR-REG-002: JSON Schema 校验
        validateSchemas(request);

        // FR-VER-001: 版本号格式校验
        if (request.getVersion() != null) {
            versionService.validateVersionFormat(request.getVersion());
        }

        // SEC-TRANS-001: MCP Server URL HTTPS 优先校验
        transportSecurity.validateHttpsPreferred(request.getMcpServerUrl());

        // FR-REG-003: 工具名称唯一性校验（同 user_id 下唯一）
        checkToolNameUniqueness(userId, request.getToolName(), null);

        // 构建实体
        McpToolEntity entity = buildEntityFromRequest(request, userId);

        // FR-REG-004: 注册后默认 DRAFT 状态
        entity.setStatus("DRAFT");
        entity.setHealthStatus("UNKNOWN");

        // 生成 toolId
        entity.setToolId(generateToolId(request.getToolName()));

        // 加密 auth_config
        if (request.getAuthConfig() != null) {
            entity.setAuthConfig(encryptAuthConfig(request.getAuthConfig()));
        }

        // 序列化 JSON 字段
        serializeJsonFields(entity, request);

        entity.setCreatedBy(userId);
        entity.setUpdatedBy(userId);

        repository.insert(entity);

        // SEC-AUDIT-001: 注册审计日志
        auditService.recordRegisterAudit(userId, entity.getToolId(), entity.getToolName(),
            toJsonString(entity));

        // FR-REG-001: 注册后 Redis 缓存同步（主动失效列表缓存）
        invalidateListCache(userId);

        log.info("Registered MCP tool: toolId={}, toolName={}, userId={}",
            entity.getToolId(), entity.getToolName(), userId);

        return buildRegisterResponse(entity);
    }

    // ======================== P2.3 工具信息管理 ========================

    @Override
    @Transactional
    public ToolDetailResponse updateTool(String toolId, ToolRegisterRequest request) {
        String userId = UserContext.getUserId();
        McpToolEntity entity = getToolEntityOrThrow(userId, toolId);

        // SEC-AUTH-003: 校验用户是否有修改该工具的权限
        checkPermission(userId, List.of("mcp:tool:update"));

        // SEC-AUDIT-001: 保存变更前快照
        String beforeSnapshot = toJsonString(entity);

        // FR-REG-002: JSON Schema 校验
        validateSchemas(request);

        // FR-VER-001: 版本号格式校验
        if (request.getVersion() != null) {
            versionService.validateVersionFormat(request.getVersion());
        }

        // FR-REG-003: 如果修改了 toolName，校验唯一性
        if (request.getToolName() != null && !request.getToolName().equals(entity.getToolName())) {
            checkToolNameUniqueness(userId, request.getToolName(), toolId);
            entity.setToolName(request.getToolName());
        }

        // FR-VER-003: 版本变更时保存历史
        String oldVersion = entity.getVersion();
        String newVersion = request.getVersion() != null ? request.getVersion() : oldVersion;
        boolean versionChanged = !oldVersion.equals(newVersion);

        // 更新字段
        updateEntityFields(entity, request);
        entity.setUpdatedBy(userId);

        // 版本变更时保存历史
        if (versionChanged) {
            versionService.saveVersionHistory(entity, oldVersion, newVersion, null);
        }

        repository.updateById(entity);

        // SEC-AUDIT-001: 更新审计日志
        auditService.recordUpdateAudit(userId, toolId, entity.getToolName(),
            beforeSnapshot, toJsonString(entity));

        // FR-MGMT-001: 更新后 Redis 缓存同步（主动失效 + 重写）
        invalidateListCache(userId);
        invalidateDetailCache(userId, toolId);
        // 如果工具是 ACTIVE 状态，更新 Hash 状态
        if ("ACTIVE".equals(entity.getStatus())) {
            toolStatePublisher.publishStateChange(entity);
        }

        log.info("Updated MCP tool: toolId={}, userId={}", toolId, userId);
        return buildDetailResponse(entity);
    }

    @Override
    @Transactional
    public boolean deleteTool(String toolId) {
        String userId = UserContext.getUserId();
        McpToolEntity entity = getToolEntityOrThrow(userId, toolId);

        // SEC-AUTH-003: 校验用户是否有删除该工具的权限
        checkPermission(userId, List.of("mcp:tool:delete"));

        // SEC-AUDIT-001: 保存删除前快照
        String beforeSnapshot = toJsonString(entity);

        // FR-MGMT-002: 软删除，标记为 INACTIVE
        entity.setStatus("INACTIVE");
        entity.setUpdatedBy(userId);
        repository.updateById(entity);

        // SEC-AUDIT-001: 删除审计日志
        auditService.recordDeleteAudit(userId, toolId, entity.getToolName(), beforeSnapshot);

        // 删除后 Redis 缓存同步
        invalidateListCache(userId);
        invalidateDetailCache(userId, toolId);
        // 从 Hash 中移除工具状态
        toolStatePublisher.removeToolState(entity);

        log.info("Soft deleted MCP tool: toolId={}, userId={}", toolId, userId);
        return true;
    }

    // ======================== P2.4 工具状态管理 ========================

    @Override
    @Transactional
    public ToolDetailResponse changeStatus(String toolId, ToolStatusChangeRequest request) {
        String userId = UserContext.getUserId();
        McpToolEntity entity = getToolEntityOrThrow(userId, toolId);

        // SEC-AUTH-003: 校验用户是否有变更该工具状态的权限
        checkPermission(userId, List.of("mcp:tool:status"));

        String currentStatus = entity.getStatus();
        String targetStatus = request.getStatus().toUpperCase();

        // FR-BUILTIN-003: BUILTIN 工具不可变更状态
        ToolStateMachine.checkBuiltinImmutable(entity.getToolType());

        // FR-STATUS-002: 状态流转校验
        ToolStateMachine.checkTransition(currentStatus, targetStatus);

        entity.setStatus(targetStatus);
        entity.setUpdatedBy(userId);
        repository.updateById(entity);

        // FR-STATUS-003: 状态变更后 Hash 写入 + 唤醒
        if ("ACTIVE".equals(targetStatus)) {
            toolStatePublisher.publishStateChange(entity);
        } else {
            // INACTIVE 状态从 Hash 中移除
            toolStatePublisher.removeToolState(entity);
        }

        // 失效列表缓存
        invalidateListCache(userId);
        invalidateDetailCache(userId, toolId);

        // SEC-AUDIT-001: 状态变更审计日志
        auditService.recordStatusChangeAudit(userId, toolId, entity.getToolName(),
            currentStatus, targetStatus);

        log.info("Changed MCP tool status: toolId={}, {} -> {}, userId={}",
            toolId, currentStatus, targetStatus, userId);
        return buildDetailResponse(entity);
    }

    // ======================== P2.5 工具列表查询 ========================

    @Override
    public ToolListResponse listTools(ToolQueryRequest request) {
        String userId = UserContext.getUserId();

        // NFR-PERF-001: Redis 缓存加速
        String cacheKey = McpRedisConstants.toolsListKey(userId);
        if (request.getStatus() == null && request.getCategory() == null && request.getKeyword() == null) {
            ToolListResponse cached = getCachedList(cacheKey);
            if (cached != null) {
                return cached;
            }
        }

        // 构建查询条件
        LambdaQueryWrapper<McpToolEntity> wrapper = new LambdaQueryWrapper<McpToolEntity>()
            .eq(McpToolEntity::getUserId, userId);

        // FR-DISC-004: 按状态/分类/关键词筛选
        if (request.getStatus() != null && !request.getStatus().isBlank()) {
            wrapper.eq(McpToolEntity::getStatus, request.getStatus().toUpperCase());
        }
        if (request.getCategory() != null && !request.getCategory().isBlank()) {
            wrapper.eq(McpToolEntity::getCategory, request.getCategory());
        }
        if (request.getKeyword() != null && !request.getKeyword().isBlank()) {
            wrapper.and(w -> w
                .like(McpToolEntity::getToolName, request.getKeyword())
                .or()
                .like(McpToolEntity::getDescription, request.getKeyword())
            );
        }
        wrapper.orderByDesc(McpToolEntity::getUpdatedAt);

        // 分页查询
        Page<McpToolEntity> page = repository.selectPage(
            new Page<>(request.getPage(), request.getSize()), wrapper);

        ToolListResponse response = new ToolListResponse();
        response.setTools(page.getRecords().stream()
            .map(this::buildToolSummary)
            .collect(Collectors.toList()));
        response.setTotal(page.getTotal());
        response.setPage(request.getPage());
        response.setSize(request.getSize());

        // 写入缓存（仅全量查询时缓存）
        if (request.getStatus() == null && request.getCategory() == null && request.getKeyword() == null) {
            cacheList(cacheKey, response);
        }

        return response;
    }

    @Override
    public Optional<ToolDetailResponse> getTool(String toolId) {
        String userId = UserContext.getUserId();

        // NFR-PERF-002: Redis 缓存加速
        String cacheKey = McpRedisConstants.toolDetailKey(userId, toolId);
        ToolDetailResponse cached = getCachedDetail(cacheKey);
        if (cached != null) {
            return Optional.of(cached);
        }

        return getToolEntity(toolId).map(entity -> {
            ToolDetailResponse response = buildDetailResponse(entity);
            cacheDetail(cacheKey, response);
            return response;
        });
    }

    @Override
    public ToolDiscoverResponse discoverTools() {
        String userId = UserContext.getUserId();

        // NFR-PERF-006: Redis 缓存加速
        String cacheKey = McpRedisConstants.toolsDiscoverKey(userId);
        ToolDiscoverResponse cached = getCachedDiscover(cacheKey);
        if (cached != null) {
            return cached;
        }

        // 仅返回 ACTIVE 状态工具（含 BUILTIN 类型，BUILTIN 始终为 ACTIVE）
        // FR-BUILTIN-002: 内置工具对所有用户可见（system 用户的 BUILTIN 工具 + 当前用户的 MCP 工具）
        List<McpToolEntity> activeTools = repository.selectList(
            new LambdaQueryWrapper<McpToolEntity>()
                .and(w -> w
                    .eq(McpToolEntity::getUserId, userId)
                    .or()
                    .eq(McpToolEntity::getToolType, "BUILTIN")
                )
                .eq(McpToolEntity::getStatus, "ACTIVE")
        );

        // SEC-AUTH-003: 仅返回用户有权限访问的工具
        List<String> userPermissions = getUserPermissions(userId);
        List<McpToolEntity> permittedTools = activeTools.stream()
            .filter(tool -> permissionChecker.checkPermission(tool, userPermissions))
            .collect(Collectors.toList());

        ToolDiscoverResponse response = new ToolDiscoverResponse();
        response.setTools(permittedTools.stream()
            .map(this::buildDiscoveredTool)
            .collect(Collectors.toList()));
        // MVP 阶段：snapshot_version 返回时间戳
        response.setSnapshotVersion("sv-" + Instant.now().toEpochMilli());

        cacheDiscover(cacheKey, response);
        return response;
    }

    @Override
    public Optional<McpToolEntity> getToolEntity(String toolId) {
        String userId = UserContext.getUserId();
        return Optional.ofNullable(repository.selectOne(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getUserId, userId)
                .eq(McpToolEntity::getToolId, toolId)
        ));
    }

    // ======================== P4.1 健康检查 ========================

    @Override
    public ToolHealthCheckResponse checkHealth(String toolId) {
        String userId = UserContext.getUserId();
        McpToolEntity entity = getToolEntityOrThrow(userId, toolId);

        // FR-HEALTH-002: 手动触发健康检查
        HealthCheckResult result = healthCheckScheduler.manualCheck(entity);

        ToolHealthCheckResponse response = new ToolHealthCheckResponse();
        response.setToolId(entity.getToolId());
        response.setToolName(entity.getToolName());
        response.setHealthStatus(result.isHealthy() ? "HEALTHY" : "UNHEALTHY");
        response.setLastHealthCheckAt(entity.getLastHealthCheckAt());
        response.setMessage(result.getMessage());
        response.setLatencyMs(result.getLatencyMs());
        response.setConsecutiveFailures(healthCheckScheduler.getConsecutiveFailures(toolId));
        response.setConsecutiveSuccesses(healthCheckScheduler.getConsecutiveSuccesses(toolId));

        return response;
    }

    // ======================== P4.2 版本管理 ========================

    @Override
    public ToolVersionResponse getVersionHistory(String toolId) {
        return versionService.getVersionHistory(toolId);
    }

    @Override
    @Transactional
    public ToolDetailResponse rollbackVersion(String toolId, ToolVersionRollbackRequest request) {
        McpToolEntity entity = versionService.rollbackVersion(toolId, request);
        return buildDetailResponse(entity);
    }

    // ======================== 私有方法 ========================

    private McpToolEntity getToolEntityOrThrow(String userId, String toolId) {
        McpToolEntity entity = repository.selectOne(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getUserId, userId)
                .eq(McpToolEntity::getToolId, toolId)
        );
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Tool not found: " + toolId);
        }
        return entity;
    }

    /**
     * SEC-AUTH-003: 校验用户是否拥有指定权限.
     */
    private void checkPermission(String userId, List<String> requiredPermissions) {
        if (!permissionChecker.checkPermission(userId, requiredPermissions)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "无操作权限");
        }
    }

    /**
     * 获取用户权限列表.
     */
    private List<String> getUserPermissions(String userId) {
        List<String> permissions = UserContext.getPermissions();
        return permissions != null ? permissions : List.of();
    }

    private void validateSchemas(ToolRegisterRequest request) {
        List<String> errors = new ArrayList<>();
        if (request.getInputSchema() != null) {
            errors.addAll(jsonSchemaValidator.validateSchema(request.getInputSchema(), "input_schema"));
        }
        if (request.getOutputSchema() != null) {
            errors.addAll(jsonSchemaValidator.validateSchema(request.getOutputSchema(), "output_schema"));
        }
        if (!errors.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "JSON Schema validation failed: " + String.join("; ", errors));
        }
    }

    private void checkToolNameUniqueness(String userId, String toolName, String excludeToolId) {
        LambdaQueryWrapper<McpToolEntity> wrapper = new LambdaQueryWrapper<McpToolEntity>()
            .eq(McpToolEntity::getUserId, userId)
            .eq(McpToolEntity::getToolName, toolName);
        if (excludeToolId != null) {
            wrapper.ne(McpToolEntity::getToolId, excludeToolId);
        }
        Long count = repository.selectCount(wrapper);
        if (count != null && count > 0) {
            throw new ResponseStatusException(HttpStatus.CONFLICT,
                "Tool name already exists: " + toolName);
        }
    }

    private String generateToolId(String toolName) {
        // 对中文 toolName：replaceAll 后前缀可能为空或仅含连字符，此时直接使用纯 UUID
        String prefix = toolName.replaceAll("[^a-zA-Z0-9]", "-").toLowerCase()
            .replaceAll("-+", "-")  // 合并连续连字符
            .replaceAll("^-|-$", "");  // 去除首尾连字符
        if (prefix.isEmpty()) {
            return "mcp-" + UUID.randomUUID().toString().substring(0, 12);
        }
        return "mcp-" + prefix + "-" + UUID.randomUUID().toString().substring(0, 8);
    }

    private McpToolEntity buildEntityFromRequest(ToolRegisterRequest request, String userId) {
        McpToolEntity entity = new McpToolEntity();
        entity.setUserId(userId);
        entity.setToolName(request.getToolName());
        entity.setDescription(request.getDescription());
        entity.setCategory(request.getCategory() != null ? request.getCategory() : "other");
        entity.setMcpServerUrl(request.getMcpServerUrl());
        entity.setTransport(request.getTransport() != null ? request.getTransport() : "http-sse");
        entity.setHealthCheckUrl(request.getHealthCheckUrl());
        entity.setRiskLevel(request.getRiskLevel() != null ? request.getRiskLevel() : "low");
        entity.setVersion(request.getVersion() != null ? request.getVersion() : "1.0.0");
        entity.setTimeoutSeconds(request.getTimeoutSeconds() != null ? request.getTimeoutSeconds() : 30);
        entity.setRetryCount(request.getRetryCount() != null ? request.getRetryCount() : 1);
        entity.setOwnerTeam(request.getOwnerTeam() != null ? request.getOwnerTeam() : "personal");
        return entity;
    }

    private void updateEntityFields(McpToolEntity entity, ToolRegisterRequest request) {
        if (request.getDescription() != null) entity.setDescription(request.getDescription());
        if (request.getCategory() != null) entity.setCategory(request.getCategory());
        if (request.getMcpServerUrl() != null) entity.setMcpServerUrl(request.getMcpServerUrl());
        if (request.getTransport() != null) entity.setTransport(request.getTransport());
        if (request.getHealthCheckUrl() != null) entity.setHealthCheckUrl(request.getHealthCheckUrl());
        if (request.getRiskLevel() != null) entity.setRiskLevel(request.getRiskLevel());
        if (request.getVersion() != null) entity.setVersion(request.getVersion());
        if (request.getTimeoutSeconds() != null) entity.setTimeoutSeconds(request.getTimeoutSeconds());
        if (request.getRetryCount() != null) entity.setRetryCount(request.getRetryCount());
        if (request.getOwnerTeam() != null) entity.setOwnerTeam(request.getOwnerTeam());

        // 更新 JSON 字段
        if (request.getInputSchema() != null) {
            entity.setInputSchema(toJsonString(request.getInputSchema()));
        }
        if (request.getOutputSchema() != null) {
            entity.setOutputSchema(toJsonString(request.getOutputSchema()));
        }
        if (request.getTags() != null) {
            entity.setTags(toJsonString(request.getTags()));
        }
        if (request.getPermissions() != null) {
            entity.setPermissions(toJsonString(request.getPermissions()));
        }
        if (request.getMetadata() != null) {
            entity.setMetadata(toJsonString(request.getMetadata()));
        }
        if (request.getAuthConfig() != null) {
            entity.setAuthConfig(encryptAuthConfig(request.getAuthConfig()));
        }
    }

    private void serializeJsonFields(McpToolEntity entity, ToolRegisterRequest request) {
        if (request.getInputSchema() != null) {
            entity.setInputSchema(toJsonString(request.getInputSchema()));
        }
        if (request.getOutputSchema() != null) {
            entity.setOutputSchema(toJsonString(request.getOutputSchema()));
        }
        if (request.getTags() != null) {
            entity.setTags(toJsonString(request.getTags()));
        }
        if (request.getPermissions() != null) {
            entity.setPermissions(toJsonString(request.getPermissions()));
        }
        if (request.getMetadata() != null) {
            entity.setMetadata(toJsonString(request.getMetadata()));
        }
    }

    private String encryptAuthConfig(ToolRegisterRequest.AuthConfig authConfig) {
        try {
            String json = objectMapper.writeValueAsString(authConfig);
            return AesEncryptionUtil.encrypt(json);
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to serialize auth_config", e);
        }
    }

    private String toJsonString(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (JsonProcessingException e) {
            throw new RuntimeException("Failed to serialize object", e);
        }
    }

    // ======================== DTO 转换 ========================

    private ToolRegisterResponse buildRegisterResponse(McpToolEntity entity) {
        ToolRegisterResponse response = new ToolRegisterResponse();
        response.setToolId(entity.getToolId());
        response.setToolName(entity.getToolName());
        response.setStatus(entity.getStatus());
        response.setVersion(entity.getVersion());
        response.setCreatedAt(entity.getCreatedAt());
        return response;
    }

    private ToolDetailResponse buildDetailResponse(McpToolEntity entity) {
        ToolDetailResponse response = new ToolDetailResponse();
        response.setToolId(entity.getToolId());
        response.setToolName(entity.getToolName());
        response.setToolType(entity.getToolType());
        response.setDescription(entity.getDescription());
        response.setCategory(entity.getCategory());
        response.setTags(parseJsonToList(entity.getTags()));
        response.setMcpServerUrl(entity.getMcpServerUrl());
        response.setTransport(entity.getTransport());
        response.setHealthCheckUrl(entity.getHealthCheckUrl());
        response.setInputSchema(parseJsonToMap(entity.getInputSchema()));
        response.setOutputSchema(parseJsonToMap(entity.getOutputSchema()));
        response.setPermissions(parseJsonToList(entity.getPermissions()));
        response.setRiskLevel(entity.getRiskLevel());
        response.setVersion(entity.getVersion());
        response.setTimeoutSeconds(entity.getTimeoutSeconds());
        response.setRetryCount(entity.getRetryCount());
        // SEC-DATA-004: auth_config 仅显示类型
        response.setAuthConfigType(extractAuthConfigType(entity.getAuthConfig()));
        response.setStatus(entity.getStatus());
        response.setHealthStatus(entity.getHealthStatus());
        response.setLastHealthCheckAt(entity.getLastHealthCheckAt());
        response.setOwnerTeam(entity.getOwnerTeam());
        response.setMetadata(parseJsonToMap(entity.getMetadata()));
        response.setCreatedAt(entity.getCreatedAt());
        response.setUpdatedAt(entity.getUpdatedAt());
        response.setCreatedBy(entity.getCreatedBy());
        response.setUpdatedBy(entity.getUpdatedBy());
        return response;
    }

    private ToolListResponse.ToolSummary buildToolSummary(McpToolEntity entity) {
        ToolListResponse.ToolSummary summary = new ToolListResponse.ToolSummary();
        summary.setToolId(entity.getToolId());
        summary.setToolName(entity.getToolName());
        summary.setToolType(entity.getToolType());
        summary.setDescription(entity.getDescription());
        summary.setCategory(entity.getCategory());
        summary.setTags(parseJsonToList(entity.getTags()));
        summary.setVersion(entity.getVersion());
        summary.setStatus(entity.getStatus());
        summary.setHealthStatus(entity.getHealthStatus());
        summary.setPermissions(parseJsonToList(entity.getPermissions()));
        summary.setMcpServerUrl(entity.getMcpServerUrl());
        summary.setTransport(entity.getTransport());
        summary.setRiskLevel(entity.getRiskLevel());
        summary.setOwnerTeam(entity.getOwnerTeam());
        summary.setCreatedAt(entity.getCreatedAt());
        summary.setUpdatedAt(entity.getUpdatedAt());
        return summary;
    }

    private ToolDiscoverResponse.DiscoveredTool buildDiscoveredTool(McpToolEntity entity) {
        ToolDiscoverResponse.DiscoveredTool tool = new ToolDiscoverResponse.DiscoveredTool();
        tool.setToolId(entity.getToolId());
        tool.setToolName(entity.getToolName());
        tool.setToolType(entity.getToolType());
        tool.setDescription(entity.getDescription());
        tool.setCategory(entity.getCategory());
        tool.setVersion(entity.getVersion());
        tool.setInputSchema(parseJsonToMap(entity.getInputSchema()));
        tool.setOutputSchema(parseJsonToMap(entity.getOutputSchema()));
        tool.setPermissions(parseJsonToList(entity.getPermissions()));
        tool.setMcpServerUrl(entity.getMcpServerUrl());
        tool.setTransport(entity.getTransport());
        tool.setTimeoutSeconds(entity.getTimeoutSeconds());
        tool.setRetryCount(entity.getRetryCount());
        tool.setRiskLevel(entity.getRiskLevel());
        return tool;
    }

    /**
     * 提取 auth_config 中的类型信息（不暴露密钥值）.
     */
    private String extractAuthConfigType(String encryptedAuthConfig) {
        if (encryptedAuthConfig == null || encryptedAuthConfig.isBlank()) {
            return null;
        }
        try {
            String decrypted = AesEncryptionUtil.decrypt(encryptedAuthConfig);
            Map<String, Object> config = objectMapper.readValue(decrypted, new TypeReference<>() {});
            Object type = config.get("type");
            return type != null ? type.toString() : "unknown";
        } catch (Exception e) {
            log.warn("Failed to extract auth_config type", e);
            return "unknown";
        }
    }

    // ======================== JSON 解析辅助 ========================

    private List<String> parseJsonToList(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            return objectMapper.readValue(json, new TypeReference<List<String>>() {});
        } catch (JsonProcessingException e) {
            log.warn("Failed to parse JSON list: {}", json);
            return null;
        }
    }

    private Map<String, Object> parseJsonToMap(String json) {
        if (json == null || json.isBlank()) return null;
        try {
            return objectMapper.readValue(json, new TypeReference<Map<String, Object>>() {});
        } catch (JsonProcessingException e) {
            log.warn("Failed to parse JSON map: {}", json);
            return null;
        }
    }

    // ======================== Redis 缓存操作 ========================

    private void invalidateListCache(String userId) {
        String key = McpRedisConstants.toolsListKey(userId);
        redisTemplate.delete(key);
        // 同时失效发现缓存
        redisTemplate.delete(McpRedisConstants.toolsDiscoverKey(userId));
    }

    private void invalidateDetailCache(String userId, String toolId) {
        String key = McpRedisConstants.toolDetailKey(userId, toolId);
        redisTemplate.delete(key);
    }

    private void cacheList(String key, ToolListResponse response) {
        try {
            String json = objectMapper.writeValueAsString(response);
            redisTemplate.opsForValue().set(key, json,
                Duration.ofSeconds(McpRedisConstants.TOOLS_LIST_TTL_SECONDS));
        } catch (JsonProcessingException e) {
            log.warn("Failed to cache tool list", e);
        }
    }

    private ToolListResponse getCachedList(String key) {
        try {
            Object cached = redisTemplate.opsForValue().get(key);
            if (cached != null) {
                return objectMapper.readValue(cached.toString(), ToolListResponse.class);
            }
        } catch (Exception e) {
            log.warn("Failed to read cached tool list", e);
        }
        return null;
    }

    private void cacheDetail(String key, ToolDetailResponse response) {
        try {
            String json = objectMapper.writeValueAsString(response);
            redisTemplate.opsForValue().set(key, json,
                Duration.ofSeconds(McpRedisConstants.TOOL_DETAIL_TTL_SECONDS));
        } catch (JsonProcessingException e) {
            log.warn("Failed to cache tool detail", e);
        }
    }

    private ToolDetailResponse getCachedDetail(String key) {
        try {
            Object cached = redisTemplate.opsForValue().get(key);
            if (cached != null) {
                return objectMapper.readValue(cached.toString(), ToolDetailResponse.class);
            }
        } catch (Exception e) {
            log.warn("Failed to read cached tool detail", e);
        }
        return null;
    }

    private void cacheDiscover(String key, ToolDiscoverResponse response) {
        try {
            String json = objectMapper.writeValueAsString(response);
            redisTemplate.opsForValue().set(key, json,
                Duration.ofSeconds(McpRedisConstants.TOOLS_DISCOVER_TTL_SECONDS));
        } catch (JsonProcessingException e) {
            log.warn("Failed to cache tool discover", e);
        }
    }

    private ToolDiscoverResponse getCachedDiscover(String key) {
        try {
            Object cached = redisTemplate.opsForValue().get(key);
            if (cached != null) {
                return objectMapper.readValue(cached.toString(), ToolDiscoverResponse.class);
            }
        } catch (Exception e) {
            log.warn("Failed to read cached tool discover", e);
        }
        return null;
    }
}
