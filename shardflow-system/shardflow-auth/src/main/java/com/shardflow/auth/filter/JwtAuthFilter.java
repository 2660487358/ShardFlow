package com.shardflow.auth.filter;

import cn.dev33.satoken.stp.StpUtil;
import com.shardflow.usercontext.context.UserContext;
import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;

import java.io.IOException;

@Component
public class JwtAuthFilter implements Filter {

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) req;
        HttpServletResponse response = (HttpServletResponse) res;

        String path = request.getRequestURI();
        if (path.startsWith("/auth/") || path.equals("/health")) {
            chain.doFilter(req, res);
            return;
        }

        try {
            String loginId = (String) StpUtil.getLoginIdByToken(
                request.getHeader("Authorization") != null
                    ? request.getHeader("Authorization").replace("Bearer ", "")
                    : ""
            );
            UserContext.setUserId(loginId);
            chain.doFilter(req, res);
        } catch (Exception e) {
            response.sendError(401, "Unauthorized");
        }
    }
}
