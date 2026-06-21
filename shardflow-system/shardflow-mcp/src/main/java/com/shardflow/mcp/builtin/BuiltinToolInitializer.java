package com.shardflow.mcp.builtin;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.McpToolEntity;
import com.shardflow.mcp.publisher.ToolStatePublisher;
import com.shardflow.mcp.repository.McpToolRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

/**
 * 内置工具初始化器.
 *
 * <p>应用启动时自动注册内置工具到 MCP 注册中心 (FR-BUILTIN-001, FR-BUILTIN-003)。
 * 内置工具特征：
 * <ul>
 *   <li>tool_type = BUILTIN</li>
 *   <li>status 始终为 ACTIVE，不可变更</li>
 *   <li>mcp_server_url 为 NULL（本地执行，不走 MCP Server）</li>
 *   <li>transport = builtin</li>
 * </ul>
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class BuiltinToolInitializer implements CommandLineRunner {

    private final McpToolRepository repository;
    private final ObjectMapper objectMapper;
    private final ToolStatePublisher toolStatePublisher;

    /** 系统内置用户 ID，用于注册内置工具。 */
    private static final String SYSTEM_USER_ID = "system";

    /** 内置工具定义列表。 */
    private static final List<BuiltinToolDef> BUILTIN_TOOLS = List.of(
        BuiltinToolDef.builder()
            .toolName("web_search")
            .description("联网搜索：通过搜索引擎获取最新信息")
            .category("search")
            .permissions(List.of("search:read"))
            .riskLevel("low")
            .inputSchema(Map.of(
                "type", "object",
                "required", List.of("query"),
                "properties", Map.of(
                    "query", Map.of("type", "string", "description", "搜索关键词"),
                    "max_results", Map.of("type", "integer", "description", "最大结果数", "default", 5)
                )
            ))
            .build(),
        BuiltinToolDef.builder()
            .toolName("read_file")
            .description("读取指定文件内容")
            .category("file")
            .permissions(List.of("repo:read"))
            .riskLevel("low")
            .inputSchema(Map.of(
                "type", "object",
                "required", List.of("path"),
                "properties", Map.of(
                    "path", Map.of("type", "string", "description", "文件路径"),
                    "encoding", Map.of("type", "string", "description", "文件编码", "default", "utf-8")
                )
            ))
            .build(),
        BuiltinToolDef.builder()
            .toolName("write_file")
            .description("写入文件内容")
            .category("file")
            .permissions(List.of("repo:write"))
            .riskLevel("medium")
            .inputSchema(Map.of(
                "type", "object",
                "required", List.of("path", "content"),
                "properties", Map.of(
                    "path", Map.of("type", "string", "description", "文件路径"),
                    "content", Map.of("type", "string", "description", "写入内容"),
                    "encoding", Map.of("type", "string", "description", "文件编码", "default", "utf-8")
                )
            ))
            .build(),
        BuiltinToolDef.builder()
            .toolName("code_analyze")
            .description("代码静态分析和语义理解")
            .category("development")
            .permissions(List.of("repo:read"))
            .riskLevel("low")
            .inputSchema(Map.of(
                "type", "object",
                "required", List.of("path", "query"),
                "properties", Map.of(
                    "path", Map.of("type", "string", "description", "代码文件路径"),
                    "query", Map.of("type", "string", "description", "分析查询问题")
                )
            ))
            .build()
    );

    @Override
    public void run(String... args) {
        int registered = 0;
        int skipped = 0;

        for (BuiltinToolDef def : BUILTIN_TOOLS) {
            try {
                // 检查是否已注册（按 system user + tool_name 查找）
                Long count = repository.selectCount(
                    new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<McpToolEntity>()
                        .eq(McpToolEntity::getUserId, SYSTEM_USER_ID)
                        .eq(McpToolEntity::getToolName, def.getToolName())
                );

                if (count != null && count > 0) {
                    skipped++;
                    continue;
                }

                // 构建内置工具实体
                McpToolEntity entity = new McpToolEntity();
                entity.setUserId(SYSTEM_USER_ID);
                entity.setToolId("builtin-" + def.getToolName());
                entity.setToolName(def.getToolName());
                entity.setToolType("BUILTIN");
                entity.setDescription(def.getDescription());
                entity.setCategory(def.getCategory());
                entity.setPermissions(toJson(def.getPermissions()));
                entity.setRiskLevel(def.getRiskLevel());
                entity.setInputSchema(toJson(def.getInputSchema()));
                entity.setTransport("builtin");
                // 内置工具无外部 MCP Server URL
                entity.setMcpServerUrl(null);
                // 内置工具始终 ACTIVE
                entity.setStatus("ACTIVE");
                entity.setHealthStatus("HEALTHY");
                entity.setVersion("1.0.0");
                entity.setTimeoutSeconds(60);
                entity.setRetryCount(0);
                entity.setOwnerTeam("system");
                entity.setCreatedBy(SYSTEM_USER_ID);
                entity.setUpdatedBy(SYSTEM_USER_ID);

                repository.insert(entity);

                // 发布到 Redis Hash（让 Python 端可发现）
                toolStatePublisher.publishStateChange(entity);

                registered++;
                log.info("Registered builtin tool: {}", def.getToolName());
            } catch (Exception e) {
                log.error("Failed to register builtin tool: {}", def.getToolName(), e);
            }
        }

        log.info("Builtin tool initialization complete: registered={}, skipped={}", registered, skipped);
    }

    private String toJson(Object obj) {
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            throw new RuntimeException("Failed to serialize object", e);
        }
    }

    /**
     * 内置工具定义内部类.
     */
    @lombok.Builder
    @lombok.Data
    private static class BuiltinToolDef {
        private String toolName;
        private String description;
        private String category;
        private List<String> permissions;
        private String riskLevel;
        private Map<String, Object> inputSchema;
    }
}
