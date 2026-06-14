package com.shardflow.kb.service;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.function.Supplier;

@Slf4j
@Service
public class GrpcCircuitBreaker {

    private final CircuitBreaker circuitBreaker;

    public GrpcCircuitBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .permittedNumberOfCallsInHalfOpenState(1)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .build();

        CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(config);
        this.circuitBreaker = registry.circuitBreaker("grpc-knowledge");
        this.circuitBreaker.getEventPublisher()
            .onStateTransition(event -> log.warn("gRPC CB: {} -> {}", event.getStateTransition().getFromState(),
                event.getStateTransition().getToState()));
    }

    public <T> T execute(Supplier<T> supplier, Supplier<T> fallback) {
        try {
            return circuitBreaker.executeSupplier(() -> {
                try {
                    return supplier.get();
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });
        } catch (Exception e) {
            log.warn("gRPC circuit breaker open or call failed: {}", e.getMessage());
            return fallback.get();
        }
    }
}
