package com.shardflow.config.controller;

import com.shardflow.common.dto.Result;
import com.shardflow.common.entity.AgentConfigEntity;
import com.shardflow.common.entity.CustomModelEntity;
import com.shardflow.config.service.ConfigService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/v1")
@RequiredArgsConstructor
public class ConfigController {

    private final ConfigService configService;

    // ── Custom Models ──

    @GetMapping("/models/custom")
    public Result<Map<String, Object>> listCustomModels() {
        List<CustomModelEntity> models = configService.listModels(UserContext.getUserId());
        return Result.ok(Map.of("models", models, "total", models.size()));
    }

    @PostMapping("/models/custom")
    public Result<CustomModelEntity> createCustomModel(@RequestBody CustomModelEntity model) {
        model.setUserId(UserContext.getUserId());
        return Result.ok(configService.createModel(model));
    }

    @PutMapping("/models/custom/{id}")
    public Result<?> updateCustomModel(@PathVariable String id, @RequestBody CustomModelEntity updates) {
        return configService.updateModel(id, updates)
            .map(Result::ok)
            .orElse(Result.fail(404, "Custom model not found"));
    }

    @DeleteMapping("/models/custom/{id}")
    public Result<?> deleteCustomModel(@PathVariable String id) {
        boolean deleted = configService.deleteModel(id);
        return deleted ? Result.ok(Map.of("deleted", true)) : Result.fail(404, "Custom model not found");
    }

    // ── Agent Configs ──

    @GetMapping("/agents")
    public Result<Map<String, Object>> listAgentConfigs() {
        List<AgentConfigEntity> agents = configService.listAgents(UserContext.getUserId());
        return Result.ok(Map.of("agents", agents, "total", agents.size()));
    }

    @PostMapping("/agents")
    public Result<AgentConfigEntity> createAgentConfig(@RequestBody AgentConfigEntity agent) {
        agent.setUserId(UserContext.getUserId());
        return Result.ok(configService.createAgent(agent));
    }

    @PutMapping("/agents/{id}")
    public Result<?> updateAgentConfig(@PathVariable String id, @RequestBody AgentConfigEntity updates) {
        return configService.updateAgent(id, updates)
            .map(Result::ok)
            .orElse(Result.fail(404, "Agent config not found"));
    }

    @DeleteMapping("/agents/{id}")
    public Result<?> deleteAgentConfig(@PathVariable String id) {
        boolean deleted = configService.deleteAgent(id);
        return deleted ? Result.ok(Map.of("deleted", true)) : Result.fail(404, "Agent config not found");
    }

    // ── Available Models (merged builtin + custom) ──

    @GetMapping("/models/available")
    public Result<Map<String, Object>> getAvailableModels() {
        return Result.ok(Map.of("models", configService.getAvailableModels(UserContext.getUserId())));
    }

    // ── Model Config (service-to-service, for Python Agent) ──

    @GetMapping("/models/{modelId}/config")
    public Result<?> getModelConfig(@PathVariable String modelId,
                                     @RequestHeader(value = "X-API-Key", required = false) String apiKey) {
        return configService.getModelConfig(modelId)
            .map(Result::ok)
            .orElse(Result.fail(404, "Model not found or disabled: " + modelId));
    }

    // ── Verify Custom Model Connectivity ──

    @PostMapping("/models/custom/verify")
    public Result<Map<String, Object>> verifyCustomModel(@RequestBody Map<String, String> body) {
        String modelId = body.get("model_id");
        if (modelId == null || modelId.isBlank()) {
            return Result.fail(400, "model_id is required");
        }
        Map<String, Object> result = configService.verifyCustomModel(modelId, UserContext.getUserId());
        return Result.ok(result);
    }

    // ── Admin: Builtin Model Management ──

    @GetMapping("/admin/models/builtin")
    public Result<Map<String, Object>> listBuiltinModels() {
        return Result.ok(Map.of("models", configService.listBuiltinModels()));
    }

    @PutMapping("/admin/models/builtin/{modelId}/toggle")
    public Result<?> toggleBuiltinModel(@PathVariable String modelId, @RequestBody Map<String, Boolean> body) {
        boolean enabled = body.getOrDefault("enabled", true);
        boolean ok = configService.toggleBuiltinModel(modelId, enabled);
        return ok ? Result.ok(Map.of("model_id", modelId, "enabled", enabled))
                  : Result.fail(404, "Builtin model not found: " + modelId);
    }
}
