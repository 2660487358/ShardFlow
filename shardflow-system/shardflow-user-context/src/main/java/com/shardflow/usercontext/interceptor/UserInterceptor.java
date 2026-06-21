package com.shardflow.usercontext.interceptor;

import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

/**
 * 用户上下文拦截器 (C-4.1-01b, C-10.2-01)。
 * 从请求头提取 userId、tenantId、traceId、requestId 注入 ThreadLocal，
 * 供 RLS 上下文注入与链路追踪透传使用。
 */
@Component
public class UserInterceptor implements HandlerInterceptor {

    private static final Logger log = LoggerFactory.getLogger(UserInterceptor.class);

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        String userId = request.getHeader("X-User-Id");
        if (userId != null && !userId.isBlank()) {
            UserContext.setUserId(userId);
        }
        // C-4.1-01b: 透传 tenant_id
        String tenantId = request.getHeader("X-Tenant-Id");
        if (tenantId != null && !tenantId.isBlank()) {
            UserContext.setTenantId(tenantId);
        }
        // C-10.2-01: 透传 trace_id / request_id
        String traceId = request.getHeader("X-Trace-ID");
        if (traceId != null && !traceId.isBlank()) {
            UserContext.setTraceId(traceId);
        }
        String requestId = request.getHeader("X-Request-ID");
        if (requestId != null && !requestId.isBlank()) {
            UserContext.setRequestId(requestId);
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        UserContext.clear();
    }
}
