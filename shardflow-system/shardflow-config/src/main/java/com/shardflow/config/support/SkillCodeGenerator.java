package com.shardflow.config.support;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.config.entity.SkillRegistryEntity;
import com.shardflow.config.repository.SkillRegistryRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.UUID;

/**
 * Skill 编码生成器.
 *
 * <p>Per Skills管理需求规格文档 DR-4 / 实施计划 P2.2.11.
 * <p>格式: SKILL-{8位UUID短码}（如 SKILL-a1b2c3d4）。
 * <p>算法: UUID v4 去连字符取前8位十六进制字符 + 前缀 "SKILL-"。
 * <p>碰撞概率约 1/4.3亿，碰撞时重试，最多3次。数据库层有 UNIQUE 约束作为最终防线。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class SkillCodeGenerator {

    private static final String PREFIX = "SKILL-";
    private static final int CODE_LENGTH = 8;
    private static final int MAX_RETRIES = 3;

    private final SkillRegistryRepository skillRegistryRepo;

    /**
     * 生成唯一的 skill_code.
     *
     * @return 格式为 SKILL-{8位十六进制} 的编码
     * @throws IllegalStateException 3次重试后仍碰撞（理论上不会发生）
     */
    public String generate() {
        for (int attempt = 0; attempt < MAX_RETRIES; attempt++) {
            String code = generateSingleCode();
            if (!exists(code)) {
                return code;
            }
            log.warn("Skill code collision detected, retrying: {} (attempt {})", code, attempt + 1);
        }
        throw new IllegalStateException("Failed to generate unique skill_code after " + MAX_RETRIES + " attempts");
    }

    private String generateSingleCode() {
        String uuid = UUID.randomUUID().toString().replace("-", "");
        return PREFIX + uuid.substring(0, CODE_LENGTH);
    }

    private boolean exists(String skillCode) {
        Long count = skillRegistryRepo.selectCount(
            new LambdaQueryWrapper<SkillRegistryEntity>()
                .eq(SkillRegistryEntity::getSkillCode, skillCode)
        );
        return count != null && count > 0;
    }
}
