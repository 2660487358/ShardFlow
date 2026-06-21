package com.shardflow.callback.service;

import java.util.Map;

/**
 * 回调服务接口（CB-01~CB-12 + kb_shard 回调）。
 * <p>
 * 规则条款：C-4.8（回调接口）、C-4.20（幂等）、C-3.3~C-3.10（各业务域回调）。
 */
public interface CallbackService {

    // CB-01: 会话完成回调
    Map<String, Object> sessionComplete(Map<String, Object> body);

    // CB-02: 审计日志写入回调
    Map<String, Object> writeAudit(Map<String, Object> body);

    // CB-03: 进度上报回调
    Map<String, Object> reportProgress(Map<String, Object> body);

    // CB-04: 状态包保存回调（会话状态摘要）
    Map<String, Object> saveShard(Map<String, Object> body);

    // CB-06: 画像保存回调
    Map<String, Object> saveProfile(Map<String, Object> body);

    // CB-07: 记忆写入回调
    Map<String, Object> saveMemory(Map<String, Object> body);

    // CB-04/12: 策略记录保存回调
    Map<String, Object> saveStrategyRecord(Map<String, Object> body);

    // ===== S4.6 新增回调接口 =====

    /**
     * CB-08: 记忆删除回调。
     * <p>
     * DELETE /api/v1/callback/memory/{key}
     *
     * @param userId 用户ID
     * @param key    记忆键
     * @return 操作结果
     */
    Map<String, Object> deleteMemory(String userId, String key);

    /**
     * CB-09: 会话摘要回调。
     * <p>
     * POST /api/v1/callback/session-summary
     * Python 生成摘要后回调 Java 异步归档 PG。
     *
     * @param body 摘要内容（session_id, user_id, summary, version, token_count 等）
     * @return 归档结果
     */
    Map<String, Object> saveSessionSummary(Map<String, Object> body);

    /**
     * CB-11: 策略删除回调。
     * <p>
     * DELETE /api/v1/callback/strategies/{recordId}
     *
     * @param recordId 策略记录ID
     * @return 操作结果
     */
    Map<String, Object> deleteStrategy(String recordId);

    /**
     * CB-12: 策略保存回调（显式 save 路径）。
     * <p>
     * POST /api/v1/callback/strategies/save
     * 与 CB-04 功能一致，路径统一为 /strategies/save。
     *
     * @param body 策略记录内容
     * @return 保存结果
     */
    Map<String, Object> saveStrategy(Map<String, Object> body);

    /**
     * KB Shard 状态包回调（C-4.5）。
     * <p>
     * POST /api/v1/callback/kb-shard
     * Python 推理层通过回调写入/更新状态包。
     *
     * @param body 状态包内容
     * @return 操作结果
     */
    Map<String, Object> saveKbShard(Map<String, Object> body);
}
