package com.shardflow.common.interceptor;

import com.shardflow.common.context.UserIdProvider;
import org.apache.ibatis.executor.Executor;
import org.apache.ibatis.mapping.MappedStatement;
import org.apache.ibatis.plugin.*;
import org.apache.ibatis.session.RowBounds;
import org.apache.ibatis.session.ResultHandler;
import org.apache.ibatis.cache.CacheKey;
import org.apache.ibatis.mapping.BoundSql;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;

import java.sql.Connection;
import java.sql.PreparedStatement;

/**
 * RLS 行级安全上下文拦截器 (C-4.1-01b)。
 * <p>
 * 在每次 MyBatis query/update 执行前，将当前用户ID通过
 * {@code set_config('app.current_user_id', ?, false)} 注入到 PostgreSQL 会话变量中，
 * 使 RLS 策略 ({@code user_id = current_setting('app.current_user_id', true)}) 生效。
 * <p>
 * 规则条款：C-4.1-01a (数据库层 RLS)、C-4.1-01b (服务层注入 user_id)、C-4.3-04g (禁止绕过 RLS)。
 */
@Intercepts({
    @Signature(type = Executor.class, method = "query",
               args = {MappedStatement.class, Object.class, RowBounds.class, ResultHandler.class,
                       CacheKey.class, BoundSql.class}),
    @Signature(type = Executor.class, method = "update",
               args = {MappedStatement.class, Object.class})
})
public class RlsContextInterceptor implements Interceptor {

    private static final Logger log = LoggerFactory.getLogger(RlsContextInterceptor.class);

    private static final String SET_CONFIG_SQL = "SELECT set_config('app.current_user_id', ?, false)";

    @Autowired(required = false)
    private UserIdProvider userIdProvider;

    @Override
    public Object intercept(Invocation invocation) throws Throwable {
        String userId = (userIdProvider != null) ? userIdProvider.getCurrentUserId() : null;
        // 始终设置上下文，即使为空也清除连接池中可能残留的旧值
        String effectiveUserId = (userId != null && !userId.isBlank()) ? userId : "";
        try {
            Executor executor = (Executor) invocation.getTarget();
            Connection connection = executor.getTransaction().getConnection();
            try (PreparedStatement ps = connection.prepareStatement(SET_CONFIG_SQL)) {
                ps.setString(1, effectiveUserId);
                ps.execute();
            }
        } catch (Exception e) {
            log.debug("RLS context injection skipped: {}", e.getMessage());
        }
        return invocation.proceed();
    }

    @Override
    public Object plugin(Object target) {
        return Plugin.wrap(target, this);
    }
}
