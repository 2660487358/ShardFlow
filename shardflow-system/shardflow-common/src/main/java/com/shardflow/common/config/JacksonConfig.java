package com.shardflow.common.config;

import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class JacksonConfig {

    @Bean
    public ObjectMapper objectMapper() {
        // Jackson 3 默认 WRITE_DATES_AS_TIMESTAMPS=false（ISO-8601 字符串），
        // 无需再显式禁用；JavaTimeModule 已内置，无需手动注册
        return JsonMapper.builder().build();
    }
}
