package com.shardflow.kb.config;

import io.minio.MinioClient;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "shardflow.minio")
public class MinioConfig {

    private String endpoint = "http://localhost:9000";
    private String accessKey = "minioadmin";
    private String secretKey = "minioadmin";
    private String bucket = "shardflow-kb";

    public void setEndpoint(String endpoint) { this.endpoint = endpoint; }
    public String getEndpoint() { return endpoint; }
    public void setAccessKey(String accessKey) { this.accessKey = accessKey; }
    public String getAccessKey() { return accessKey; }
    public void setSecretKey(String secretKey) { this.secretKey = secretKey; }
    public String getSecretKey() { return secretKey; }
    public void setBucket(String bucket) { this.bucket = bucket; }
    public String getBucket() { return bucket; }

    @Bean
    public MinioClient minioClient() {
        return MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
    }
}
