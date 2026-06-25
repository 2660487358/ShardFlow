package com.shardflow.mcp.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.McpQuickTemplateEntity;
import com.shardflow.mcp.repository.McpQuickTemplateRepository;
import com.shardflow.mcp.service.TemplateRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class TemplateRegistryImpl implements TemplateRegistry {

    private final McpQuickTemplateRepository repository;
    private final ObjectMapper objectMapper;

    @Override
    public Optional<McpQuickTemplateEntity> getById(String templateId) {
        LambdaQueryWrapper<McpQuickTemplateEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(McpQuickTemplateEntity::getTemplateId, templateId)
               .eq(McpQuickTemplateEntity::getStatus, "ACTIVE");
        return Optional.ofNullable(repository.selectOne(wrapper));
    }

    @Override
    public List<McpQuickTemplateEntity> list(String category, String keyword) {
        LambdaQueryWrapper<McpQuickTemplateEntity> wrapper = new LambdaQueryWrapper<>();
        wrapper.eq(McpQuickTemplateEntity::getStatus, "ACTIVE");

        if (category != null && !category.isEmpty()) {
            wrapper.eq(McpQuickTemplateEntity::getCategory, category);
        }

        if (keyword != null && !keyword.isEmpty()) {
            wrapper.and(w -> w
                .like(McpQuickTemplateEntity::getDisplayName, keyword)
                .or()
                .like(McpQuickTemplateEntity::getDescription, keyword)
                .or()
                .like(McpQuickTemplateEntity::getTags, keyword)
            );
        }

        wrapper.orderByAsc(McpQuickTemplateEntity::getSortOrder);

        return repository.selectList(wrapper);
    }

    @Override
    public void initializeFromSeed() {
        Long count = repository.selectCount(null);
        if (count > 0) {
            log.info("Template table already initialized, skip seed");
            return;
        }

        try {
            ClassPathResource resource = new ClassPathResource("templates/seed-templates.json");
            if (!resource.exists()) {
                log.warn("Seed templates file not found: templates/seed-templates.json");
                return;
            }

            try (InputStream is = resource.getInputStream()) {
                List<McpQuickTemplateEntity> templates = objectMapper.readValue(
                    is,
                    new TypeReference<List<McpQuickTemplateEntity>>() {}
                );

                for (McpQuickTemplateEntity template : templates) {
                    repository.insert(template);
                }

                log.info("Initialized {} templates from seed", templates.size());
            }
        } catch (IOException e) {
            log.error("Failed to initialize templates from seed", e);
        }
    }
}
