package com.shardflow.usercontext.context;

import java.util.List;

public class UserContext {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();
    private static final ThreadLocal<List<String>> CURRENT_PERMISSIONS = new ThreadLocal<>();

    public static void setUserId(String userId) { CURRENT_USER.set(userId); }
    public static String getUserId() { return CURRENT_USER.get(); }
    public static void setPermissions(List<String> permissions) { CURRENT_PERMISSIONS.set(permissions); }
    public static List<String> getPermissions() { return CURRENT_PERMISSIONS.get(); }
    public static void clear() { CURRENT_USER.remove(); CURRENT_PERMISSIONS.remove(); }
}
