package com.shardflow.mcp.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.dto.mcp.ToolVersionResponse;
import com.shardflow.common.dto.mcp.ToolVersionRollbackRequest;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.common.entity.McpToolVersionEntity;
import com.shardflow.mcp.publisher.ToolStatePublisher;
import com.shardflow.mcp.repository.McpToolRepository;
import com.shardflow.mcp.repository.McpVersionRepository;
import com.shardflow.mcp.service.McpAuditService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.time.Instant;
import java.util.List;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * MCP 工具版本管理服务.
 * 实现版本号校验、多版本共存、版本历史保存、版本查询、版本回退 (FR-VER-001~004).
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class McpVersionService {

    private final McpVersionRepository versionRepository;
    private final McpToolRepository toolRepository;
    private final ToolStatePublisher toolStatePublisher;
    private final RedisTemplate<String, Object> redisTemplate;
    private final McpAuditService auditService;

    /** MAJOR.MINOR.PATCH 版本号正则 */
    private static final Pattern VERSION_PATTERN = Pattern.compile(
        "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$"
    );

    /**
     * 校验版本号格式 (FR-VER-001).
     * 必须符合 MAJOR.MINOR.PATCH 格式.
     *
     * @param version 版本号
     * @throws ResponseStatusException 如果格式非法
     */
    public void validateVersionFormat(String version) {
        if (version == null || version.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Version is required");
        }
        if (!VERSION_PATTERN.matcher(version).matches()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST,
                "Invalid version format: " + version + ". Expected MAJOR.MINOR.PATCH (e.g., 1.0.0)");
        }
    }

    /**
     * 保存版本历史 (FR-VER-003).
     * 工具更新时自动保存当前版本到 mcp_tool_version 表.
     *
     * @param tool       工具实体
     * @param oldVersion 旧版本号（更新前）
     * @param newVersion 新版本号
     * @param changelog  变更说明
     */
    @Transactional
    public void saveVersionHistory(McpToolEntity tool, String oldVersion, String newVersion, String changelog) {
        McpToolVersionEntity versionEntity = new McpToolVersionEntity();
        versionEntity.setUserId(tool.getUserId());
        versionEntity.setToolId(tool.getToolId());
        versionEntity.setVersion(oldVersion); // 保存旧版本号
        versionEntity.setInputSchema(tool.getInputSchema());
        versionEntity.setOutputSchema(tool.getOutputSchema());
        versionEntity.setDescription(tool.getDescription());
        versionEntity.setChangelog(changelog != null ? changelog :
            "Updated to version " + newVersion);
        versionEntity.setStatus("active");
        versionEntity.setCreatedBy(
            UserContext.getUserId() != null ? UserContext.getUserId() : "system");

        versionRepository.insert(versionEntity);

        // 将旧版本标记为 archived（保留最近 20 个 active 版本）
        archiveOldVersions(tool.getUserId(), tool.getToolId());

        log.info("Saved version history: toolId={}, oldVersion={}, newVersion={}",
            tool.getToolId(), tool.getVersion(), newVersion);
    }

    /**
     * 查询版本历史 (FR-VER-003).
     *
     * @param toolId 工具ID
     * @return 版本历史响应
     */
    public ToolVersionResponse getVersionHistory(String toolId) {
        String userId = UserContext.getUserId();
        McpToolEntity tool = getToolOrThrow(userId, toolId);

        List<McpToolVersionEntity> versions = versionRepository.selectList(
            new LambdaQueryWrapper<McpToolVersionEntity>()
                .eq(McpToolVersionEntity::getUserId, userId)
                .eq(McpToolVersionEntity::getToolId, toolId)
                .orderByDesc(McpToolVersionEntity::getCreatedAt)
        );

        ToolVersionResponse response = new ToolVersionResponse();
        response.setToolId(toolId);
        response.setToolName(tool.getToolName());
        response.setCurrentVersion(tool.getVersion());
        response.setVersions(versions.stream()
            .map(this::toVersionEntry)
            .collect(Collectors.toList()));

        return response;
    }

    /**
     * 版本回退 (FR-VER-004).
     * 回退到指定版本或上一个版本，更新工具元数据 + 刷新 Hash.
     *
     * @param toolId  工具ID
     * @param request 回退请求
     * @return 更新后的工具详情
     */
    @Transactional
    public McpToolEntity rollbackVersion(String toolId, ToolVersionRollbackRequest request) {
        String userId = UserContext.getUserId();
        McpToolEntity tool = getToolOrThrow(userId, toolId);

        // 确定目标版本
        String targetVersion = request.getTargetVersion();
        McpToolVersionEntity targetVersionEntity;

        if (targetVersion != null && !targetVersion.isBlank()) {
            // 回退到指定版本
            targetVersionEntity = versionRepository.selectOne(
                new LambdaQueryWrapper<McpToolVersionEntity>()
                    .eq(McpToolVersionEntity::getUserId, userId)
                    .eq(McpToolVersionEntity::getToolId, toolId)
                    .eq(McpToolVersionEntity::getVersion, targetVersion)
            );
            if (targetVersionEntity == null) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "Version not found: " + targetVersion);
            }
        } else {
            // 回退到上一个版本
            List<McpToolVersionEntity> recentVersions = versionRepository.selectList(
                new LambdaQueryWrapper<McpToolVersionEntity>()
                    .eq(McpToolVersionEntity::getUserId, userId)
                    .eq(McpToolVersionEntity::getToolId, toolId)
                    .orderByDesc(McpToolVersionEntity::getCreatedAt)
                    .last("LIMIT 1")
            );
            if (recentVersions.isEmpty()) {
                throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                    "No version history available for rollback");
            }
            targetVersionEntity = recentVersions.get(0);
        }

        // 保存当前版本到历史（回退前的版本）
        String oldVersion = tool.getVersion();
        saveVersionHistory(tool, oldVersion, targetVersionEntity.getVersion(),
            "Rollback from " + oldVersion + " to " + targetVersionEntity.getVersion());

        // 回退工具元数据
        tool.setVersion(targetVersionEntity.getVersion());
        tool.setInputSchema(targetVersionEntity.getInputSchema());
        tool.setOutputSchema(targetVersionEntity.getOutputSchema());
        if (targetVersionEntity.getDescription() != null) {
            tool.setDescription(targetVersionEntity.getDescription());
        }
        tool.setUpdatedBy(userId);
        toolRepository.updateById(tool);

        // FR-VER-004: 回退后自动刷新 Hash
        if ("ACTIVE".equals(tool.getStatus())) {
            toolStatePublisher.publishStateChange(tool);
        }

        // 失效缓存
        invalidateCaches(userId, toolId);

        // SEC-AUDIT-001: 版本回退审计日志
        auditService.recordRollbackAudit(userId, toolId, tool.getToolName(),
            targetVersionEntity.getVersion());

        log.info("Rolled back tool {} from {} to {}",
            toolId, oldVersion, targetVersionEntity.getVersion());

        return tool;
    }

    /**
     * 检查同一工具是否支持多版本共存 (FR-VER-002).
     * 默认使用最新 ACTIVE 版本.
     *
     * @param userId  用户ID
     * @param toolId  工具ID
     * @param version 版本号
     * @return 该版本是否为最新 ACTIVE 版本
     */
    public boolean isLatestActiveVersion(String userId, String toolId, String version) {
        McpToolEntity tool = toolRepository.selectOne(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getUserId, userId)
                .eq(McpToolEntity::getToolId, toolId)
        );
        return tool != null && tool.getVersion().equals(version);
    }

    // ======================== 私有方法 ========================

    private McpToolEntity getToolOrThrow(String userId, String toolId) {
        McpToolEntity entity = toolRepository.selectOne(
            new LambdaQueryWrapper<McpToolEntity>()
                .eq(McpToolEntity::getUserId, userId)
                .eq(McpToolEntity::getToolId, toolId)
        );
        if (entity == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND,
                "Tool not found: " + toolId);
        }
        return entity;
    }

    private ToolVersionResponse.VersionEntry toVersionEntry(McpToolVersionEntity entity) {
        ToolVersionResponse.VersionEntry entry = new ToolVersionResponse.VersionEntry();
        entry.setId(entity.getId());
        entry.setVersion(entity.getVersion());
        entry.setDescription(entity.getDescription());
        entry.setChangelog(entity.getChangelog());
        entry.setStatus(entity.getStatus());
        entry.setCreatedAt(entity.getCreatedAt());
        entry.setCreatedBy(entity.getCreatedBy());
        return entry;
    }

    /**
     * 归档旧版本，保留最近 20 个 active 版本 (NFR-MAINT).
     */
    private void archiveOldVersions(String userId, String toolId) {
        List<McpToolVersionEntity> activeVersions = versionRepository.selectList(
            new LambdaQueryWrapper<McpToolVersionEntity>()
                .eq(McpToolVersionEntity::getUserId, userId)
                .eq(McpToolVersionEntity::getToolId, toolId)
                .eq(McpToolVersionEntity::getStatus, "active")
                .orderByDesc(McpToolVersionEntity::getCreatedAt)
        );

        // 保留最近 20 个版本，其余标记为 archived
        if (activeVersions.size() > 20) {
            List<McpToolVersionEntity> toArchive = activeVersions.subList(20, activeVersions.size());
            for (McpToolVersionEntity v : toArchive) {
                v.setStatus("archived");
                versionRepository.updateById(v);
            }
            log.debug("Archived {} old versions for tool {}", toArchive.size(), toolId);
        }
    }

    private void invalidateCaches(String userId, String toolId) {
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsListKey(userId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolDetailKey(userId, toolId));
        redisTemplate.delete(com.shardflow.common.config.McpRedisConstants.toolsDiscoverKey(userId));
    }
}
