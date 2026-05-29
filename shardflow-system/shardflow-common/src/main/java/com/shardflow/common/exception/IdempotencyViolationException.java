package com.shardflow.common.exception;

public class IdempotencyViolationException extends RuntimeException {
    public IdempotencyViolationException(String idempotencyKey) {
        super("Duplicate request: " + idempotencyKey);
    }
}
