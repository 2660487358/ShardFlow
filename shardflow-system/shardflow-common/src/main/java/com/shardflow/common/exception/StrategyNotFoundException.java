package com.shardflow.common.exception;

public class StrategyNotFoundException extends RuntimeException {
    public StrategyNotFoundException(String id) { super("Strategy not found: " + id); }
}
