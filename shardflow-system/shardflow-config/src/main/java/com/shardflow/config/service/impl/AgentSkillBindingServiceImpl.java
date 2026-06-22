package com.shardflow.config.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import tools.jackson.databind.ObjectMapper;
import com.shardflow.common.entity.AgentConfigEntity;
import com.shardflow.config.repository.AgentConfigRepository;
import com.shardflow.config.dto.AgentSkillBindingRequest;
import com.shardflow.config.dto.SkillDetailDTO;
import com.shardflow.config.entity.AgentSkillBindingEntity;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.AgentSkillBindingRepository;
import com.shardflow.config.repository.SkillRegistryRepository;
import com.shardflow.config.service.AgentSkillBindingService;
import com.shardflow.config.service.SkillCacheEvictor;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * Agent-Skill 绑定服务实现.
 *
 * <p>Per Skills管理需求规格文档 FR-5 / 实施计划 P4.1.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class AgentSkillBindingServiceImpl implements AgentSkillBindingService {

    private final AgentSkillBindingRepository bindingRepository;
    private final SkillRegistryRepository skillRegistryRepository;
    private final AgentConfigRepository agentConfigRepository;
    private final SkillCacheEvictor cacheEvictor;
    private final ObjectMapper objectMapper;

    @Override
    @Transactional
    public void updateAgentSkills(String agentId, AgentSkillBindingRequest request) {
        String userId = UserContext.getUserId();

        // 校验 Agent 归属
        AgentConfigEntity agent = findAgent(agentId, userId);
        if (agent == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Agent not found: " + agentId);
        }

        List<AgentSkillBindingRequest.BindingItem> items = request.getBindings();
        if (items == null) {
            items = List.of();
        }

        // 校验所有 Skill 存在且当前用户有 EXECUTE 权限
        List<Long> skillIds = items.stream()
            .map(AgentSkillBindingRequest.BindingItem::getSkillId)
            .filter(Objects::nonNull)
            .distinct()
            .collect(Collectors.toList());

        if (!skillIds.isEmpty()) {
            List<SkillRegistryEntity> skills = skillRegistryRepository.selectList(
                new LambdaQueryWrapper<SkillRegistryEntity>()
                    .in(SkillRegistryEntity::getId, skillIds)
            );
            if (skills.size() != skillIds.size()) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "部分 Skill 不存在");
            }
            for (SkillRegistryEntity skill : skills) {
                if (!userId.equals(skill.getUserId()) && !"official".equals(skill.getTrustTier())) {
                    throw new ResponseStatusException(HttpStatus.FORBIDDEN,
                        "无权限绑定 Skill: " + skill.getSkillCode());
                }
            }
        }

        // 全量替换：先删除现有绑定
        bindingRepository.delete(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getAgentId, agentId)
        );

        // 插入新绑定
        for (AgentSkillBindingRequest.BindingItem item : items) {
            AgentSkillBindingEntity entity = new AgentSkillBindingEntity();
            entity.setAgentId(agentId);
            entity.setSkillId(item.getSkillId());
            entity.setBoundVersion(item.getBoundVersion() != null ? item.getBoundVersion() : "");
            entity.setBindingType(item.getBindingType() != null ? item.getBindingType() : "optional");
            entity.setPriority(item.getPriority() != null ? item.getPriority() : 0);
            entity.setConfigOverride(toJsonString(item.getConfigOverride()));
            entity.setEnabled(item.getEnabled() != null ? item.getEnabled() : 1);
            entity.setCreatedBy(userId);
            bindingRepository.insert(entity);

            // 失效该 Skill 的缓存
            SkillRegistryEntity skill = skillRegistryRepository.selectById(item.getSkillId());
            if (skill != null) {
                cacheEvictor.evictOnBindingChange(userId, skill.getSkillCode(), agentId);
            }
        }

        log.info("Updated agent skills: agentId={}, count={}, userId={}", agentId, items.size(), userId);
    }

    @Override
    public List<AgentSkillBindingRequest.BindingItem> listAgentSkills(String agentId) {
        String userId = UserContext.getUserId();
        AgentConfigEntity agent = findAgent(agentId, userId);
        if (agent == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Agent not found: " + agentId);
        }

        List<AgentSkillBindingEntity> bindings = bindingRepository.selectList(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getAgentId, agentId)
                .orderByDesc(AgentSkillBindingEntity::getPriority)
        );

        return bindings.stream().map(this::toBindingItem).collect(Collectors.toList());
    }

    @Override
    public void deleteByAgentId(String agentId) {
        bindingRepository.delete(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getAgentId, agentId)
        );
        log.info("Deleted agent skill bindings: agentId={}", agentId);
    }

    @Override
    public List<SkillDetailDTO.AgentRef> listSkillAgents(String skillCode) {
        String userId = UserContext.getUserId();
        SkillRegistryEntity skill = skillRegistryRepository.selectOne(
            new LambdaQueryWrapper<SkillRegistryEntity>()
                .eq(SkillRegistryEntity::getSkillCode, skillCode)
                .eq(SkillRegistryEntity::getUserId, userId)
        );
        if (skill == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Skill not found: " + skillCode);
        }

        List<AgentSkillBindingEntity> bindings = bindingRepository.selectList(
            new LambdaQueryWrapper<AgentSkillBindingEntity>()
                .eq(AgentSkillBindingEntity::getSkillId, skill.getId())
                .orderByDesc(AgentSkillBindingEntity::getPriority)
        );

        return bindings.stream().map(this::toAgentRef).collect(Collectors.toList());
    }

    private AgentConfigEntity findAgent(String agentId, String userId) {
        AgentConfigEntity agent = agentConfigRepository.selectOne(
            new LambdaQueryWrapper<AgentConfigEntity>()
                .eq(AgentConfigEntity::getAgentCode, agentId)
                .eq(AgentConfigEntity::getUserId, userId)
        );
        if (agent != null) {
            return agent;
        }
        // 兼容数字 ID：追加 userId 过滤避免越权
        try {
            Long numericId = Long.parseLong(agentId);
            return agentConfigRepository.selectOne(
                new LambdaQueryWrapper<AgentConfigEntity>()
                    .eq(AgentConfigEntity::getId, numericId)
                    .eq(AgentConfigEntity::getUserId, userId)
            );
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private AgentSkillBindingRequest.BindingItem toBindingItem(AgentSkillBindingEntity entity) {
        AgentSkillBindingRequest.BindingItem item = new AgentSkillBindingRequest.BindingItem();
        item.setSkillId(entity.getSkillId());
        item.setBoundVersion(entity.getBoundVersion());
        item.setBindingType(entity.getBindingType());
        item.setPriority(entity.getPriority());
        item.setConfigOverride(parseObjectMap(entity.getConfigOverride()));
        item.setEnabled(entity.getEnabled());
        return item;
    }

    private SkillDetailDTO.AgentRef toAgentRef(AgentSkillBindingEntity binding) {
        SkillDetailDTO.AgentRef ref = new SkillDetailDTO.AgentRef();
        ref.setId(binding.getId());
        ref.setAgentCode(binding.getAgentId());
        ref.setBindingType(binding.getBindingType());
        ref.setPriority(binding.getPriority());

        // 查询 Agent 真实名称
        AgentConfigEntity agent = agentConfigRepository.selectOne(
            new LambdaQueryWrapper<AgentConfigEntity>()
                .eq(AgentConfigEntity::getAgentCode, binding.getAgentId())
        );
        ref.setName(agent != null ? agent.getName() : binding.getAgentId());
        return ref;
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> parseObjectMap(String json) {
        if (json == null || json.isBlank()) return Map.of();
        try {
            return objectMapper.readValue(json, Map.class);
        } catch (Exception e) {
            log.warn("Failed to parse config_override: {}", json, e);
            return Map.of();
        }
    }

    private String toJsonString(Object obj) {
        if (obj == null) return null;
        try {
            return objectMapper.writeValueAsString(obj);
        } catch (Exception e) {
            log.warn("Failed to serialize config_override: {}", obj, e);
            return null;
        }
    }
}