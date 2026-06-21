package com.shardflow.kb.service;

import com.shardflow.common.entity.KbShardEntity;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 知识库状态包服务接口（C-4.5 通用 ContextShard 状态包）。
 * <p>
 * 规则条款：C-4.5（状态包管理）、C-6.5（版本号乐观锁）、C-3.4（三级存取）、C-4.8（回调接口）。
 * <p>
 * 提供状态包的创建、查询、更新（带版本控制）、归档和回调聚合能力。
 */
public interface KbShardService {

    /**
     * 创建状态包。
     *
     * @param entity 预填充的状态包实体（shardId 可空，自动生成）
     * @return 创建后的实体（含生成的 shardId 和 version=1）
     */
    KbShardEntity createShard(KbShardEntity entity);

    /**
     * 按 shardId 查询状态包。
     */
    Optional<KbShardEntity> getShard(String shardId);

    /**
     * 按所有者和类型查询状态包列表。
     */
    List<KbShardEntity> listByOwner(String ownerId, String shardType);

    /**
     * 更新状态包（带版本号乐观锁）。
     * <p>
     * 如果 expectedVersion 与当前版本不匹配，返回 empty。
     *
     * @param shardId        状态包ID
     * @param entity         更新内容
     * @param expectedVersion 期望的版本号（乐观锁）
     * @return 更新后的实体，版本不匹配时返回 empty
     */
    Optional<KbShardEntity> updateShard(String shardId, KbShardEntity entity, Integer expectedVersion);

    /**
     * 归档状态包（标记为 archived，不再可写）。
     */
    Optional<KbShardEntity> archiveShard(String shardId);

    /**
     * 软删除状态包。
     */
    boolean deleteShard(String shardId);

    /**
     * 回调聚合：从 Python 推理层回调写入状态包。
     * <p>
     * 解析 Map body，创建或更新状态包。
     *
     * @param body 回调请求体
     * @return 操作结果
     */
    Map<String, Object> saveFromCallback(Map<String, Object> body);
}
