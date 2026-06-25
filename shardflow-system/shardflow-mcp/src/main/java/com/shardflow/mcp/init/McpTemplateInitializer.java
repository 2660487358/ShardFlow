package com.shardflow.mcp.init;

import com.shardflow.mcp.service.TemplateRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * MCP 模板数据初始化器.
 * 应用启动时自动从 Seed JSON 初始化模板数据.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class McpTemplateInitializer implements ApplicationRunner {

    private final TemplateRegistry templateRegistry;

    @Override
    public void run(ApplicationArguments args) {
        log.info("Initializing MCP templates from seed...");
        templateRegistry.initializeFromSeed();
        log.info("MCP templates initialization completed");
    }
}
