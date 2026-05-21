package com.shardflow.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.shardflow")
public class KbApplication {
    public static void main(String[] args) {
        SpringApplication.run(KbApplication.class, args);
    }
}
