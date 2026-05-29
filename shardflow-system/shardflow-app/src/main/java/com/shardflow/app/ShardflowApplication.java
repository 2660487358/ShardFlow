package com.shardflow.app;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(scanBasePackages = "com.shardflow")
@MapperScan("com.shardflow.**.repository")
@EnableScheduling
@EnableAsync
public class ShardflowApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShardflowApplication.class, args);
    }
}
