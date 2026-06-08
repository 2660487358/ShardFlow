package com.shardflow.auth.service;

import java.util.Map;

public interface AuthService {

    Map<String, Object> login(String username, String password);

    Map<String, Object> register(String username, String password);

    Map<String, Object> refresh(String refreshToken);

    void logout(String token, String refreshToken);
}
