package com.shardflow.common.exception;

public class UserMismatchException extends RuntimeException {
    public UserMismatchException(String expected, String actual) {
        super("User mismatch: expected=" + expected + " actual=" + actual);
    }
}
