package com.shardflow.kb.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Getter
@Setter
@Configuration
@ConfigurationProperties(prefix = "shardflow.grpc")
public class GrpcConfig {

    private String pythonHost = "localhost";
    private int pythonPort = 50051;
    private int timeoutSeconds = 10;
}
