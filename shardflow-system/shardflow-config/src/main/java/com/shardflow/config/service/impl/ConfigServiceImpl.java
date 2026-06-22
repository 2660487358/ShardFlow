package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.entity.AgentConfigEntity;
import com.shardflow.common.entity.BuiltinModelEntity;
import com.shardflow.common.entity.CustomModelEntity;
import com.shardflow.common.entity.ModelAuditLogEntity;
import com.shardflow.common.util.AesEncryptionUtil;
import com.shardflow.config.repository.AgentConfigRepository;
import com.shardflow.config.repository.BuiltinModelRepository;
import com.shardflow.config.repository.CustomModelRepository;
import com.shardflow.config.repository.ModelAuditLogRepository;
import com.shardflow.config.service.AgentSkillBindingService;
import com.shardflow.config.service.ConfigService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
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
public class ConfigServiceImpl implements ConfigService {

    private final CustomModelRepository customModelRepository;
    private final AgentConfigRepository agentConfigRepository;
    private final BuiltinModelRepository builtinModelRepository;
    private final ModelAuditLogRepository modelAuditLogRepository;
    private final AgentSkillBindingService bindingService;

    // ── Startup Initialization ──
    // Builtin model seed data is handled by schema.sql (ON CONFLICT ... DO NOTHING),
    // no need for @PostConstruct initialization here.

    // ── Custom Models ──

    @Override
    public List<CustomModelEntity> listModels(String userId) {
        return customModelRepository.selectList(
            new LambdaQueryWrapper<CustomModelEntity>()
                .eq(CustomModelEntity::getUserId, userId)
                .orderByDesc(CustomModelEntity::getCreatedAt)
        );
    }

    @Override
    public Optional<CustomModelEntity> getModel(String id) {
        // id can be either numeric PK or model_code
        try {
            long numericId = Long.parseLong(id);
            return Optional.ofNullable(customModelRepository.selectById(numericId));
        } catch (NumberFormatException e) {
            return Optional.ofNullable(customModelRepository.selectOne(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, id)));
        }
    }

    @Override
    @Transactional
    public CustomModelEntity createModel(CustomModelEntity model) {
        if (model.getModelCode() == null || model.getModelCode().isBlank()) {
            model.setModelCode("custom-" + UUID.randomUUID().toString().substring(0, 8));
        }
        model.setEnabled(model.getEnabled() != null ? model.getEnabled() : true);
        model.setIsVerified(model.getIsVerified() != null ? model.getIsVerified() : false);

        // Encrypt API key if provided in api_key_id (plaintext from frontend)
        if (model.getApiKeyId() != null && !model.getApiKeyId().isBlank()
                && !"****".equals(model.getApiKeyId())) {
            model.setApiKeyEncrypted(AesEncryptionUtil.encrypt(model.getApiKeyId()));
            model.setApiKeyId("encrypted"); // placeholder, actual key in api_key_encrypted
        }

        customModelRepository.insert(model);
        auditLog(model.getUserId(), "CREATE", model.getModelCode(), "CUSTOM",
            "Created custom model: " + model.getName(), true);
        return model;
    }

    @Override
    @Transactional
    public Optional<CustomModelEntity> updateModel(String id, CustomModelEntity updates) {
        CustomModelEntity existing;
        try {
            long numericId = Long.parseLong(id);
            existing = customModelRepository.selectById(numericId);
        } catch (NumberFormatException e) {
            existing = customModelRepository.selectOne(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, id));
        }
        if (existing == null) return Optional.empty();

        // Encrypt new API key if provided
        if (updates.getApiKeyId() != null && !updates.getApiKeyId().isBlank()
                && !"****".equals(updates.getApiKeyId())) {
            existing.setApiKeyEncrypted(AesEncryptionUtil.encrypt(updates.getApiKeyId()));
            existing.setApiKeyId("encrypted");
        }

        // Merge non-null fields from updates into existing to avoid empty SET clause
        if (updates.getName() != null) existing.setName(updates.getName());
        if (updates.getProvider() != null) existing.setProvider(updates.getProvider());
        if (updates.getBaseUrl() != null) existing.setBaseUrl(updates.getBaseUrl());
        if (updates.getModel() != null) existing.setModel(updates.getModel());
        if (updates.getCapabilities() != null) existing.setCapabilities(updates.getCapabilities());
        if (updates.getContextWindow() != null) existing.setContextWindow(updates.getContextWindow());
        if (updates.getEnabled() != null) existing.setEnabled(updates.getEnabled());
        if (updates.getModelCode() != null) existing.setModelCode(updates.getModelCode());

        customModelRepository.updateById(existing);
        auditLog(existing.getUserId(), "UPDATE", existing.getModelCode(), "CUSTOM",
            "Updated custom model: " + existing.getName(), true);
        return Optional.of(customModelRepository.selectById(existing.getId()));
    }

    @Override
    public boolean deleteModel(String id) {
        CustomModelEntity existing;
        try {
            long numericId = Long.parseLong(id);
            existing = customModelRepository.selectById(numericId);
        } catch (NumberFormatException e) {
            existing = customModelRepository.selectOne(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, id));
        }
        if (existing != null) {
            auditLog(existing.getUserId(), "DELETE", existing.getModelCode(), "CUSTOM",
                "Deleted custom model: " + existing.getName(), true);
        }
        try {
            long numericId = Long.parseLong(id);
            return customModelRepository.deleteById(numericId) > 0;
        } catch (NumberFormatException e) {
            return customModelRepository.delete(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, id)) > 0;
        }
    }

    // ── Agent Configs ──

    @Override
    public List<AgentConfigEntity> listAgents(String userId) {
        return agentConfigRepository.selectList(
            new LambdaQueryWrapper<AgentConfigEntity>()
                .eq(AgentConfigEntity::getUserId, userId)
                .orderByDesc(AgentConfigEntity::getUpdatedAt)
        );
    }

    @Override
    public Optional<AgentConfigEntity> getAgent(String id) {
        try {
            long numericId = Long.parseLong(id);
            return Optional.ofNullable(agentConfigRepository.selectById(numericId));
        } catch (NumberFormatException e) {
            return Optional.ofNullable(agentConfigRepository.selectOne(
                new LambdaQueryWrapper<AgentConfigEntity>().eq(AgentConfigEntity::getAgentCode, id)));
        }
    }

    @Override
    public AgentConfigEntity createAgent(AgentConfigEntity agent) {
        if (agent.getAgentCode() == null || agent.getAgentCode().isBlank()) {
            agent.setAgentCode("agent-" + UUID.randomUUID().toString().substring(0, 8));
        }
        agentConfigRepository.insert(agent);
        return agent;
    }

    @Override
    public Optional<AgentConfigEntity> updateAgent(String id, AgentConfigEntity updates) {
        AgentConfigEntity existing;
        try {
            long numericId = Long.parseLong(id);
            existing = agentConfigRepository.selectById(numericId);
        } catch (NumberFormatException e) {
            existing = agentConfigRepository.selectOne(
                new LambdaQueryWrapper<AgentConfigEntity>().eq(AgentConfigEntity::getAgentCode, id));
        }
        if (existing == null) return Optional.empty();

        // Merge non-null fields from updates into existing to avoid empty SET clause
        if (updates.getName() != null) existing.setName(updates.getName());
        if (updates.getDescription() != null) existing.setDescription(updates.getDescription());
        if (updates.getModelId() != null) existing.setModelId(updates.getModelId());
        if (updates.getSystemPrompt() != null) existing.setSystemPrompt(updates.getSystemPrompt());
        if (updates.getTemperature() != null) existing.setTemperature(updates.getTemperature());
        if (updates.getMaxTokens() != null) existing.setMaxTokens(updates.getMaxTokens());
        if (updates.getTools() != null) existing.setTools(updates.getTools());
        if (updates.getAgentCode() != null) existing.setAgentCode(updates.getAgentCode());

        agentConfigRepository.updateById(existing);
        return Optional.of(agentConfigRepository.selectById(existing.getId()));
    }

    @Override
    @Transactional
    public boolean deleteAgent(String id) {
        // P4.1.7: Agent 删除时级联解绑 Skill
        bindingService.deleteByAgentId(id);
        try {
            long numericId = Long.parseLong(id);
            return agentConfigRepository.deleteById(numericId) > 0;
        } catch (NumberFormatException e) {
            return agentConfigRepository.delete(
                new LambdaQueryWrapper<AgentConfigEntity>().eq(AgentConfigEntity::getAgentCode, id)) > 0;
        }
    }

    // ── Available Models (merged builtin + custom) ──

    @Override
    public List<Map<String, Object>> getAvailableModels(String userId) {
        List<Map<String, Object>> models = new ArrayList<>();

        // Builtin models from database
        List<BuiltinModelEntity> builtins = builtinModelRepository.selectList(
            new LambdaQueryWrapper<BuiltinModelEntity>()
                .eq(BuiltinModelEntity::getIsEnabled, true)
                .orderByAsc(BuiltinModelEntity::getSortOrder)
        );
        for (BuiltinModelEntity b : builtins) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("key", b.getModelCode());
            m.put("label", b.getName());
            m.put("provider", b.getProvider());
            m.put("model", b.getModel());
            m.put("capabilities", b.getCapabilities());
            m.put("context_window", b.getContextWindow());
            m.put("type", "builtin");
            models.add(m);
        }

        // User custom models
        List<CustomModelEntity> customs = customModelRepository.selectList(
            new LambdaQueryWrapper<CustomModelEntity>()
                .eq(CustomModelEntity::getUserId, userId)
                .eq(CustomModelEntity::getEnabled, true)
                .orderByDesc(CustomModelEntity::getCreatedAt)
        );
        for (CustomModelEntity c : customs) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("key", c.getModelCode());
            m.put("label", c.getName());
            m.put("provider", c.getProvider());
            m.put("model", c.getModel());
            m.put("capabilities", c.getCapabilities());
            m.put("context_window", c.getContextWindow());
            m.put("type", "custom");
            m.put("is_verified", c.getIsVerified());
            models.add(m);
        }

        return models;
    }

    // ── Model Config (for Python Agent) ──

    @Override
    public Optional<Map<String, Object>> getModelConfig(String modelId) {
        // Custom model - lookup by model_code
        if (modelId.startsWith("custom-")) {
            CustomModelEntity custom = customModelRepository.selectOne(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, modelId));
            if (custom == null || !Boolean.TRUE.equals(custom.getEnabled())) {
                return Optional.empty();
            }
            String apiKey = null;
            if (custom.getApiKeyEncrypted() != null && !custom.getApiKeyEncrypted().isBlank()) {
                apiKey = AesEncryptionUtil.decrypt(custom.getApiKeyEncrypted());
            }
            auditLog(custom.getUserId(), "DECRYPT", modelId, "CUSTOM",
                "API key decrypted for inference", true);

            Map<String, Object> config = new LinkedHashMap<>();
            config.put("model_id", modelId);
            config.put("model", custom.getModel());
            config.put("base_url", custom.getBaseUrl() != null ? custom.getBaseUrl() : "https://api.openai.com/v1");
            config.put("api_key", apiKey != null ? apiKey : "");
            config.put("provider", custom.getProvider());
            config.put("capabilities", custom.getCapabilities());
            config.put("context_window", custom.getContextWindow());
            config.put("type", "custom");
            return Optional.of(config);
        }

        // Builtin model - lookup by model_code
        BuiltinModelEntity builtin = builtinModelRepository.selectOne(
            new LambdaQueryWrapper<BuiltinModelEntity>().eq(BuiltinModelEntity::getModelCode, modelId));
        if (builtin == null || !Boolean.TRUE.equals(builtin.getIsEnabled())) {
            return Optional.empty();
        }

        // Read API key from environment variable
        String apiKey = System.getenv(builtin.getApiKeyEnv());
        if (apiKey == null || apiKey.isBlank()) {
            // Fallback to global
            apiKey = System.getenv("SF_AGENT_LLM_API_KEY");
        }
        String baseUrl = builtin.getBaseUrl();
        if (baseUrl == null || baseUrl.isBlank()) {
            baseUrl = System.getenv("SF_AGENT_LLM_BASE_URL");
        }

        Map<String, Object> config = new LinkedHashMap<>();
        config.put("model_id", modelId);
        config.put("model", builtin.getModel());
        config.put("base_url", baseUrl);
        config.put("api_key", apiKey != null ? apiKey : "");
        config.put("provider", builtin.getProvider());
        config.put("capabilities", builtin.getCapabilities());
        config.put("context_window", builtin.getContextWindow());
        config.put("type", "builtin");
        config.put("api_key_env", builtin.getApiKeyEnv());
        return Optional.of(config);
    }

    // ── Verify Custom Model Connectivity ──

    @Override
    public Map<String, Object> verifyCustomModel(String modelId, String userId) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("model_id", modelId);

        CustomModelEntity custom;
        try {
            long numericId = Long.parseLong(modelId);
            custom = customModelRepository.selectById(numericId);
        } catch (NumberFormatException e) {
            custom = customModelRepository.selectOne(
                new LambdaQueryWrapper<CustomModelEntity>().eq(CustomModelEntity::getModelCode, modelId));
        }
        if (custom == null) {
            result.put("success", false);
            result.put("error", "Model not found");
            return result;
        }

        String apiKey = null;
        if (custom.getApiKeyEncrypted() != null && !custom.getApiKeyEncrypted().isBlank()) {
            try {
                apiKey = AesEncryptionUtil.decrypt(custom.getApiKeyEncrypted());
            } catch (Exception e) {
                result.put("success", false);
                result.put("error", "Failed to decrypt API key");
                auditLog(userId, "VERIFY", modelId, "CUSTOM", "Decryption failed", false);
                return result;
            }
        }

        if (apiKey == null || apiKey.isBlank()) {
            result.put("success", false);
            result.put("error", "No API key configured");
            auditLog(userId, "VERIFY", modelId, "CUSTOM", "No API key", false);
            return result;
        }

        String baseUrl = custom.getBaseUrl();
        if (baseUrl == null || baseUrl.isBlank()) {
            baseUrl = "https://api.openai.com/v1";
        }

        long startMs = System.currentTimeMillis();
        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/models"))
                .header("Authorization", "Bearer " + apiKey)
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());

            long latencyMs = System.currentTimeMillis() - startMs;
            boolean success = response.statusCode() == 200;

            // Update verification status
            custom.setIsVerified(success);
            customModelRepository.updateById(custom);

            result.put("success", success);
            result.put("status_code", response.statusCode());
            result.put("latency_ms", latencyMs);
            if (!success) {
                result.put("error", "HTTP " + response.statusCode());
            }
            auditLog(userId, "VERIFY", modelId, "CUSTOM",
                "status=" + response.statusCode() + " latency=" + latencyMs + "ms", success);
        } catch (Exception e) {
            long latencyMs = System.currentTimeMillis() - startMs;
            result.put("success", false);
            result.put("error", e.getMessage());
            result.put("latency_ms", latencyMs);
            auditLog(userId, "VERIFY", modelId, "CUSTOM",
                "error=" + e.getMessage(), false);
        }

        return result;
    }

    // ── Admin: Builtin Models ──

    @Override
    public List<Map<String, Object>> listBuiltinModels() {
        List<BuiltinModelEntity> all = builtinModelRepository.selectList(
            new LambdaQueryWrapper<BuiltinModelEntity>()
                .orderByAsc(BuiltinModelEntity::getSortOrder)
        );
        List<Map<String, Object>> result = new ArrayList<>();
        for (BuiltinModelEntity b : all) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", b.getModelCode());
            m.put("name", b.getName());
            m.put("provider", b.getProvider());
            m.put("model", b.getModel());
            m.put("base_url", b.getBaseUrl());
            m.put("api_key_env", b.getApiKeyEnv());
            m.put("capabilities", b.getCapabilities());
            m.put("context_window", b.getContextWindow());
            m.put("is_enabled", b.getIsEnabled());
            m.put("sort_order", b.getSortOrder());
            result.add(m);
        }
        return result;
    }

    @Override
    @Transactional
    public boolean toggleBuiltinModel(String modelId, boolean enabled) {
        BuiltinModelEntity model = builtinModelRepository.selectOne(
            new LambdaQueryWrapper<BuiltinModelEntity>().eq(BuiltinModelEntity::getModelCode, modelId));
        if (model == null) return false;
        model.setIsEnabled(enabled);
        builtinModelRepository.updateById(model);
        auditLog("admin", enabled ? "ENABLE" : "DISABLE", modelId, "BUILTIN",
            "Toggled builtin model to enabled=" + enabled, true);
        return true;
    }

    // ── Audit Logging ──

    private void auditLog(String userId, String action, String modelId, String modelType, String summary, boolean success) {
        try {
            ModelAuditLogEntity log = new ModelAuditLogEntity();
            log.setUserId(userId != null ? userId : "system");
            log.setAction(action);
            log.setModelId(modelId);
            log.setModelType(modelType);
            log.setSummary(summary != null && summary.length() > 500 ? summary.substring(0, 500) : summary);
            log.setSuccess(success);
            modelAuditLogRepository.insert(log);
        } catch (Exception e) {
            log.warn("Failed to write model audit log: {}", e.getMessage());
        }
    }
}
