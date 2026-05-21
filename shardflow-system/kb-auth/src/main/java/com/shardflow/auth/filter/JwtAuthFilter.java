package com.shardflow.auth.filter;

import com.shardflow.auth.service.JwtService;
import com.shardflow.tenant.context.TenantContext;
import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.Map;

@Component
public class JwtAuthFilter implements Filter {

    private final JwtService jwtService;

    public JwtAuthFilter(JwtService jwtService) { this.jwtService = jwtService; }

    @Override
    public void doFilter(ServletRequest req, ServletResponse res, FilterChain chain)
            throws IOException, ServletException {
        HttpServletRequest request = (HttpServletRequest) req;
        HttpServletResponse response = (HttpServletResponse) res;

        String path = request.getRequestURI();
        // Skip auth for login/register/health
        if (path.startsWith("/api/v1/auth/") || path.startsWith("/api/v1/callback/")
            || path.equals("/health")) {
            chain.doFilter(req, res);
            return;
        }

        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            try {
                Map<String, String> claims = jwtService.validateToken(header.substring(7));
                TenantContext.setTenantId(claims.get("tenant_id"));
                chain.doFilter(req, res);
                return;
            } catch (Exception e) {
                response.sendError(401, "Invalid token");
                return;
            }
        }
        response.sendError(401, "Authorization required");
    }
}
