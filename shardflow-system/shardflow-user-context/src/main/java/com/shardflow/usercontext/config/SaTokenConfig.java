package com.shardflow.usercontext.config;

import cn.dev33.satoken.context.SaHolder;
import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.jwt.StpLogicJwtForSimple;
import cn.dev33.satoken.stp.StpLogic;
import cn.dev33.satoken.stp.StpUtil;
import com.shardflow.usercontext.context.UserContext;
import com.shardflow.usercontext.interceptor.UserInterceptor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/**
 * SaToken 认证配置。
 * 使用 SaInterceptor（Spring MVC 拦截器）替代 SaServletFilter（Servlet 过滤器），
 * 确保在 Spring Boot 4 环境中 SaToken 能正确读取请求中的 JWT token。
 * 支持两种认证方式：JWT（前端用户）和 X-API-Key（服务间调用）。
 */
@Configuration
public class SaTokenConfig implements WebMvcConfigurer {

    private static final Logger log = LoggerFactory.getLogger(SaTokenConfig.class);

    private final UserInterceptor userInterceptor;

    @Value("${shardflow.java-api-key:}")
    private String javaApiKey;

    public SaTokenConfig(UserInterceptor userInterceptor) {
        this.userInterceptor = userInterceptor;
    }

    @Bean
    public StpLogic stpLogic() {
        return new StpLogicJwtForSimple();
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // 1. SaInterceptor: JWT 认证校验 + API Key 服务间认证 + 设置 UserContext
        registry.addInterceptor(new SaInterceptor(handle -> {
            // 优先检查服务间 API Key 认证
            String apiKey = SaHolder.getRequest().getHeader("X-API-Key");
            if (apiKey != null && !apiKey.isBlank()) {
                if (javaApiKey != null && !javaApiKey.isBlank() && javaApiKey.equals(apiKey)) {
                    UserContext.setUserId("service");
                    return;
                }
                // API Key 不匹配，记录日志后继续走 JWT 校验（会返回 401）
                log.warn("Invalid X-API-Key provided in service-to-service request");
            }
            // 前端用户走 JWT 认证
            StpUtil.checkLogin();
            UserContext.setUserId((String) StpUtil.getLoginId());
        })).addPathPatterns("/api/v1/**")
          .excludePathPatterns("/auth/**", "/health", "/error");

        // 2. UserInterceptor: X-User-Id header 支持 + 请求结束后清理 UserContext
        registry.addInterceptor(userInterceptor)
            .addPathPatterns("/api/v1/**");
    }
}
