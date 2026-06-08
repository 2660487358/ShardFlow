package com.shardflow.auth.service.impl;

import cn.dev33.satoken.stp.SaLoginModel;
import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.auth.repository.UserRepository;
import com.shardflow.auth.service.AuthService;
import com.shardflow.common.entity.UserEntity;
import com.shardflow.common.exception.AuthenticationException;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class AuthServiceImpl implements AuthService {

    private final UserRepository userRepository;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder(12);

    /** Access token 有效期：2 小时 */
    private static final long ACCESS_TOKEN_TIMEOUT = 7200;
    /** Refresh token 有效期：7 天 */
    private static final long REFRESH_TOKEN_TIMEOUT = 604800;

    @Override
    public Map<String, Object> login(String username, String password) {
        UserEntity user = userRepository.selectOne(
            new LambdaQueryWrapper<UserEntity>().eq(UserEntity::getUsername, username)
        );

        if (user == null || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new AuthenticationException("Invalid credentials");
        }

        return buildAuthResult(user.getUserId(), user.getRole());
    }

    @Override
    public Map<String, Object> refresh(String refreshToken) {
        Object loginId = StpUtil.getLoginIdByToken(refreshToken);
        if (loginId == null) {
            throw new AuthenticationException("Invalid or expired refresh token");
        }

        // 仅创建新的 access token，refresh token 保持不变（7 天内有效）
        StpUtil.login(loginId, new SaLoginModel()
            .setTimeout(ACCESS_TOKEN_TIMEOUT)
            .setDevice("access"));
        String newAccessToken = StpUtil.getTokenValue();

        Map<String, Object> result = new HashMap<>();
        result.put("token", newAccessToken);
        result.put("refresh_token", refreshToken);
        result.put("expires_in", ACCESS_TOKEN_TIMEOUT);
        return result;
    }

    @Override
    public Map<String, Object> register(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            throw new AuthenticationException("Username and password are required");
        }
        UserEntity existing = userRepository.selectOne(
            new LambdaQueryWrapper<UserEntity>().eq(UserEntity::getUsername, username)
        );
        if (existing != null) {
            throw new AuthenticationException("Username already exists");
        }

        UserEntity user = new UserEntity();
        user.setUsername(username);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setRole("user");
        String uid = java.util.UUID.randomUUID().toString().replace("-", "");
        user.setUserId(uid);
        userRepository.insert(user);

        return buildAuthResult(user.getUserId(), user.getRole());
    }

    @Override
    public void logout(String token, String refreshToken) {
        if (token != null && !token.isBlank()) {
            StpUtil.logoutByTokenValue(token);
        }
        if (refreshToken != null && !refreshToken.isBlank()) {
            StpUtil.logoutByTokenValue(refreshToken);
        }
    }

    /**
     * 构建双 token 认证结果：
     * 1. 先创建 access token（2h），再创建 refresh token（7d）
     * 2. is-concurrent=true + is-share=false 保证两次 login 产生独立会话
     */
    private Map<String, Object> buildAuthResult(String userId, String role) {
        // 创建 access token（短期）
        StpUtil.login(userId, new SaLoginModel()
            .setTimeout(ACCESS_TOKEN_TIMEOUT)
            .setDevice("access"));
        String accessToken = StpUtil.getTokenValue();

        // 创建 refresh token（长期）
        StpUtil.login(userId, new SaLoginModel()
            .setTimeout(REFRESH_TOKEN_TIMEOUT)
            .setDevice("refresh"));
        String refreshToken = StpUtil.getTokenValue();

        Map<String, Object> result = new HashMap<>();
        result.put("token", accessToken);
        result.put("refresh_token", refreshToken);
        result.put("expires_in", ACCESS_TOKEN_TIMEOUT);
        result.put("user_id", userId);
        result.put("role", role);
        return result;
    }
}
