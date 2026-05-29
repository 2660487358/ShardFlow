package com.shardflow.common.dto;

public record ApiError(int status, String message, String detail) {}
