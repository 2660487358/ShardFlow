package com.shardflow.common.exception;

public class ShardNotFoundException extends RuntimeException {
    public ShardNotFoundException(String id) { super("Shard not found: " + id); }
}
