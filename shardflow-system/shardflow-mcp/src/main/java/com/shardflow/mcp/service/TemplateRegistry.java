package com.shardflow.mcp.service;

import com.shardflow.common.entity.McpQuickTemplateEntity;

import java.util.List;
import java.util.Optional;

/**
 * 模板注册中心服务接口.
 * P2 阶段：模板查询、初始化.
 */
public interface TemplateRegistry {

    /**
     * 按 ID 查询单个模板.
     */
    Optional<McpQuickTemplateEntity> getById(String templateId);

    /**
     * 按分类/关键词筛选模板列表.
     *
     * @param category 分类（可选）
     * @param keyword  关键词（可选）
     * @return 模板列表
     */
    List<McpQuickTemplateEntity> list(String category, String keyword);

    /**
     * 初始化数据库模板数据（从 Seed JSON）.
     * 首次启动时若表为空则执行.
     */
    void initializeFromSeed();
}
