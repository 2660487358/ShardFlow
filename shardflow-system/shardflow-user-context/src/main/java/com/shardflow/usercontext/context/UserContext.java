package com.shardflow.usercontext.context;

public class UserContext {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    public static void setUserId(String userId) { CURRENT_USER.set(userId); }
    public static String getUserId() { return CURRENT_USER.get(); }
    public static void clear() { CURRENT_USER.remove(); }
}
