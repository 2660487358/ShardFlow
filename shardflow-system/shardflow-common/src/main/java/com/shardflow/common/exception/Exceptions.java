package com.shardflow.common.exception;

public class ShardNotFoundException extends RuntimeException {
    public ShardNotFoundException(String id) { super("Shard not found: " + id); }
}

public class StrategyNotFoundException extends RuntimeException {
    public StrategyNotFoundException(String id) { super("Strategy not found: " + id); }
}

public class TenantMismatchException extends RuntimeException {
    public TenantMismatchException(String expected, String actual) {
        super("Tenant mismatch: expected=" + expected + " actual=" + actual);
    }
}

public class IdempotencyViolationException extends RuntimeException {
    public IdempotencyViolationException(String idempotencyKey) {
        super("Duplicate request: " + idempotencyKey);
    }
}
