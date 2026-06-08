package com.shardflow.common.exception;

import cn.dev33.satoken.exception.NotLoginException;
import com.shardflow.common.dto.Result;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ShardNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Result<Void> handleShardNotFound(ShardNotFoundException e) {
        log.warn("Shard not found: {}", e.getMessage());
        return Result.fail(404, e.getMessage());
    }

    @ExceptionHandler(StrategyNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Result<Void> handleStrategyNotFound(StrategyNotFoundException e) {
        log.warn("Strategy not found: {}", e.getMessage());
        return Result.fail(404, e.getMessage());
    }

    @ExceptionHandler(UserMismatchException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public Result<Void> handleUserMismatch(UserMismatchException e) {
        log.warn("User mismatch: {}", e.getMessage());
        return Result.fail(403, e.getMessage());
    }

    @ExceptionHandler(IdempotencyViolationException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public Result<Void> handleIdempotencyViolation(IdempotencyViolationException e) {
        log.warn("Idempotency violation: {}", e.getMessage());
        return Result.fail(409, e.getMessage());
    }

    @ExceptionHandler(AuthenticationException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Result<Void> handleAuthentication(AuthenticationException e) {
        log.warn("Authentication error: {}", e.getMessage());
        return Result.fail(401, e.getMessage());
    }

    @ExceptionHandler(NotLoginException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public Result<Void> handleNotLogin(NotLoginException e) {
        log.warn("Authentication failed: {}", e.getMessage());
        return Result.fail(401, "Unauthorized");
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Result<Void> handleValidation(MethodArgumentNotValidException e) {
        String msg = e.getBindingResult().getFieldErrors().stream()
            .map(f -> f.getField() + ": " + f.getDefaultMessage())
            .reduce((a, b) -> a + "; " + b)
            .orElse("Validation failed");
        return Result.fail(400, msg);
    }

    @ExceptionHandler(Exception.class)
    @ResponseStatus(HttpStatus.INTERNAL_SERVER_ERROR)
    public Result<Void> handleGeneral(Exception e) {
        log.error("Unexpected error", e);
        return Result.fail(500, "Internal server error");
    }
}
