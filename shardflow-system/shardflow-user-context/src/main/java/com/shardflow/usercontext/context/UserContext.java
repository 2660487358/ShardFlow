package com.shardflow.usercontext.context;

import java.util.List;

/**
 * 用户上下文 (ThreadLocal)：存储当前请求的 userId、tenantId、traceId、requestId。
 * 规则条款：C-4.1-01b (Java 网关注入 user_id/tenant_id 透传)、C-10.2-01 (trace_id/request_id 透传)。
 */
public class UserContext {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();
    private static final ThreadLocal<String> CURRENT_TENANT = new ThreadLocal<>();
    private static final ThreadLocal<String> CURRENT_TRACE_ID = new ThreadLocal<>();
    private static final ThreadLocal<String> CURRENT_REQUEST_ID = new ThreadLocal<>();
    private static final ThreadLocal<List<String>> CURRENT_PERMISSIONS = new ThreadLocal<>();

    public static void setUserId(String userId) { CURRENT_USER.set(userId); }
    public static String getUserId() { return CURRENT_USER.get(); }

    public static void setTenantId(String tenantId) { CURRENT_TENANT.set(tenantId); }
    public static String getTenantId() { return CURRENT_TENANT.get(); }

    public static void setTraceId(String traceId) { CURRENT_TRACE_ID.set(traceId); }
    public static String getTraceId() { return CURRENT_TRACE_ID.get(); }

    public static void setRequestId(String requestId) { CURRENT_REQUEST_ID.set(requestId); }
    public static String getRequestId() { return CURRENT_REQUEST_ID.get(); }

    public static void setPermissions(List<String> permissions) { CURRENT_PERMISSIONS.set(permissions); }
    public static List<String> getPermissions() { return CURRENT_PERMISSIONS.get(); }

    public static void clear() {
        CURRENT_USER.remove();
        CURRENT_TENANT.remove();
        CURRENT_TRACE_ID.remove();
        CURRENT_REQUEST_ID.remove();
        CURRENT_PERMISSIONS.remove();
    }
}
