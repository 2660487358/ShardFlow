package com.shardflow.mcp.health;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

import java.time.Duration;
import java.time.Instant;

/**
 * MCP 工具健康检查执行器.
 * 调用 health_check_url 判断 MCP Server 可用性 (FR-HEALTH-001).
 *
 * <p>检查逻辑：
 * <ul>
 *   <li>HTTP GET 请求 health_check_url</li>
 *   <li>响应 2xx → HEALTHY</li>
 *   <li>超时/连接失败/非 2xx → UNHEALTHY</li>
 * </ul>
 */
@Slf4j
@Component
public class McpHealthChecker {

    private final RestTemplate restTemplate;

    public McpHealthChecker() {
        org.springframework.http.client.SimpleClientHttpRequestFactory factory =
            new org.springframework.http.client.SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofSeconds(5));
        factory.setReadTimeout(Duration.ofSeconds(30));
        this.restTemplate = new RestTemplate(factory);
    }

    /**
     * 执行健康检查.
     *
     * @param healthCheckUrl 健康检查 URL
     * @param timeoutSeconds 超时时间（秒）
     * @return 检查结果
     */
    public HealthCheckResult check(String healthCheckUrl, int timeoutSeconds) {
        if (healthCheckUrl == null || healthCheckUrl.isBlank()) {
            return HealthCheckResult.unknown("health_check_url not configured");
        }

        Instant start = Instant.now();
        try {
            ResponseEntity<String> response = restTemplate.getForEntity(
                healthCheckUrl, String.class);

            long latencyMs = Duration.between(start, Instant.now()).toMillis();

            if (response.getStatusCode().is2xxSuccessful()) {
                log.debug("Health check passed: url={}, latency={}ms", healthCheckUrl, latencyMs);
                return HealthCheckResult.healthy(latencyMs);
            } else {
                log.warn("Health check failed: url={}, status={}", healthCheckUrl, response.getStatusCode());
                return HealthCheckResult.unhealthy(
                    "HTTP " + response.getStatusCode().value(), latencyMs);
            }
        } catch (Exception e) {
            long latencyMs = Duration.between(start, Instant.now()).toMillis();
            log.warn("Health check error: url={}, error={}", healthCheckUrl, e.getMessage());
            return HealthCheckResult.unhealthy(e.getClass().getSimpleName() + ": " + e.getMessage(), latencyMs);
        }
    }

    /**
     * 健康检查结果.
     */
    public static class HealthCheckResult {

        private final boolean healthy;
        private final String message;
        private final long latencyMs;

        private HealthCheckResult(boolean healthy, String message, long latencyMs) {
            this.healthy = healthy;
            this.message = message;
            this.latencyMs = latencyMs;
        }

        public static HealthCheckResult healthy(long latencyMs) {
            return new HealthCheckResult(true, "OK", latencyMs);
        }

        public static HealthCheckResult unhealthy(String message, long latencyMs) {
            return new HealthCheckResult(false, message, latencyMs);
        }

        public static HealthCheckResult unknown(String message) {
            return new HealthCheckResult(false, message, 0);
        }

        public boolean isHealthy() {
            return healthy;
        }

        public String getMessage() {
            return message;
        }

        public long getLatencyMs() {
            return latencyMs;
        }
    }
}
