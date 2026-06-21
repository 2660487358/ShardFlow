package com.shardflow.common.context;

/**
 * 用户ID提供者接口 (解耦 shardflow-common 与 shardflow-user-context)。
 * <p>
 * shardflow-common 中的 RLS 拦截器通过此接口获取当前用户ID，
 * 具体实现由 shardflow-user-context 模块提供（委托给 UserContext ThreadLocal）。
 */
@FunctionalInterface
public interface UserIdProvider {
    /**
     * 获取当前请求的用户ID，无上下文时返回 null。
     */
    String getCurrentUserId();
}
