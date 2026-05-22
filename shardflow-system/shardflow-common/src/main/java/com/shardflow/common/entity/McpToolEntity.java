package com.shardflow.common.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "shardflow_mcp_tool")
public class McpToolEntity {

    @Id
    @Column(name = "tool_id", length = 128)
    private String toolId;

    @Column(name = "tool_name", nullable = false, length = 128)
    private String toolName;

    @Column(columnDefinition = "text")
    private String description;

    @Column(name = "mcp_server_url", length = 512)
    private String mcpServerUrl;

    @Column(name = "input_schema", columnDefinition = "jsonb")
    private String inputSchema;

    @Column(name = "output_schema", columnDefinition = "jsonb")
    private String outputSchema;

    @Column(columnDefinition = "jsonb")
    private String permissions;

    @Column(length = 32)
    private String version;

    @Column(length = 16, nullable = false)
    private String status = "ACTIVE";

    @Column(name = "last_health_check")
    private Instant lastHealthCheck;

    public McpToolEntity() {}

    public String getToolId() { return toolId; }
    public void setToolId(String toolId) { this.toolId = toolId; }
    public String getToolName() { return toolName; }
    public void setToolName(String toolName) { this.toolName = toolName; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getMcpServerUrl() { return mcpServerUrl; }
    public void setMcpServerUrl(String mcpServerUrl) { this.mcpServerUrl = mcpServerUrl; }
    public String getInputSchema() { return inputSchema; }
    public void setInputSchema(String inputSchema) { this.inputSchema = inputSchema; }
    public String getOutputSchema() { return outputSchema; }
    public void setOutputSchema(String outputSchema) { this.outputSchema = outputSchema; }
    public String getPermissions() { return permissions; }
    public void setPermissions(String permissions) { this.permissions = permissions; }
    public String getVersion() { return version; }
    public void setVersion(String version) { this.version = version; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Instant getLastHealthCheck() { return lastHealthCheck; }
    public void setLastHealthCheck(Instant lastHealthCheck) { this.lastHealthCheck = lastHealthCheck; }
}
