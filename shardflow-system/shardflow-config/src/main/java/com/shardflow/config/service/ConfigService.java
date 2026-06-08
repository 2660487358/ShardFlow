package com.shardflow.config.service;

import com.shardflow.common.entity.CustomModelEntity;
import com.shardflow.common.entity.AgentConfigEntity;
import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface ConfigService {

    // Custom Models
    List<CustomModelEntity> listModels(String userId);
    Optional<CustomModelEntity> getModel(String id);
    CustomModelEntity createModel(CustomModelEntity model);
    Optional<CustomModelEntity> updateModel(String id, CustomModelEntity updates);
    boolean deleteModel(String id);

    // Agent Configs
    List<AgentConfigEntity> listAgents(String userId);
    Optional<AgentConfigEntity> getAgent(String id);
    AgentConfigEntity createAgent(AgentConfigEntity agent);
    Optional<AgentConfigEntity> updateAgent(String id, AgentConfigEntity updates);
    boolean deleteAgent(String id);

    // Available models — merged builtin + custom
    List<Map<String, Object>> getAvailableModels(String userId);

    // Model config for Python Agent (includes decrypted api_key)
    Optional<Map<String, Object>> getModelConfig(String modelId);

    // Custom model connectivity verification
    Map<String, Object> verifyCustomModel(String modelId, String userId);

    // Admin: list all builtin models
    List<Map<String, Object>> listBuiltinModels();

    // Admin: toggle builtin model enabled status
    boolean toggleBuiltinModel(String modelId, boolean enabled);
}
