package com.shardflow.common.exception;

/**
 * 认证异常：用于登录失败、token无效/过期等场景。
 * 返回 HTTP 401，替代 RuntimeException 以避免被兜底处理器返回 500。
 */
public class AuthenticationException extends RuntimeException {

    public AuthenticationException(String message) {
        super(message);
    }
}
