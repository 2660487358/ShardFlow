package com.shardflow.usercontext.context;

import com.shardflow.common.context.UserIdProvider;
import org.springframework.stereotype.Component;

/**
 * UserIdProvider 实现：委托给 UserContext ThreadLocal。
 * 桥接 shardflow-common (RLS拦截器) 与 shardflow-user-context (UserContext)。
 */
@Component
public class UserContextUserIdProvider implements UserIdProvider {

    @Override
    public String getCurrentUserId() {
        return UserContext.getUserId();
    }
}
