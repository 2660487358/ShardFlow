package com.shardflow.usercontext.interceptor;

import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class UserInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) {
        String userId = request.getHeader("X-User-Id");
        if (userId != null && !userId.isBlank()) {
            UserContext.setUserId(userId);
            // RLS: PostgreSQL session variable will be set via a DataSource proxy
            // or TransactionAware aspect. See V2__add_rls.sql for the set_app_user() function.
            // TODO: Call SELECT set_app_user(:userId) on each new DB connection.
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response,
                                Object handler, Exception ex) {
        UserContext.clear();
    }
}
