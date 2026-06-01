package com.shardflow.usercontext.config;

import cn.dev33.satoken.context.SaHolder;
import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.filter.SaServletFilter;
import cn.dev33.satoken.jwt.StpLogicJwtForSimple;
import cn.dev33.satoken.stp.StpLogic;
import cn.dev33.satoken.stp.StpUtil;
import cn.dev33.satoken.util.SaResult;
import com.shardflow.usercontext.context.UserContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SaTokenConfig {

    @Bean
    public StpLogic stpLogic() {
        return new StpLogicJwtForSimple();
    }

    @Bean
    public SaServletFilter saServletFilter() {
        return new SaServletFilter()
            .addInclude("/api/v1/**")
            .addExclude("/auth/**", "/health", "/error")
            .setAuth(obj -> {
                StpUtil.checkLogin();
                UserContext.setUserId((String) StpUtil.getLoginId());
            })
            .setError(e -> {
                if (e instanceof NotLoginException) {
                    return SaResult.error("Unauthorized").setCode(401);
                }
                return SaResult.error("Internal server error").setCode(500);
            });
    }
}
