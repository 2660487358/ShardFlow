package com.shardflow.auth.service.impl;

import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.auth.repository.UserRepository;
import com.shardflow.auth.service.AuthService;
import com.shardflow.common.entity.UserEntity;
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

    @Override
    public Map<String, Object> login(String username, String password) {
        UserEntity user = userRepository.selectOne(
            new LambdaQueryWrapper<UserEntity>().eq(UserEntity::getUsername, username)
        );

        if (user == null || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new RuntimeException("Invalid credentials");
        }

        StpUtil.login(user.getUserId());
        String token = StpUtil.getTokenValue();

        Map<String, Object> result = new HashMap<>();
        result.put("token", token);
        result.put("user_id", user.getUserId());
        result.put("role", user.getRole());
        return result;
    }

    @Override
    public Map<String, Object> refresh(String refreshToken) {
        Object loginId = StpUtil.getLoginId();
        StpUtil.logout();
        StpUtil.login(loginId);
        String newToken = StpUtil.getTokenValue();

        Map<String, Object> result = new HashMap<>();
        result.put("token", newToken);
        return result;
    }

    @Override
    public Map<String, Object> register(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            throw new RuntimeException("Username and password are required");
        }
        UserEntity existing = userRepository.selectOne(
            new LambdaQueryWrapper<UserEntity>().eq(UserEntity::getUsername, username)
        );
        if (existing != null) {
            throw new RuntimeException("Username already exists");
        }

        UserEntity user = new UserEntity();
        user.setUsername(username);
        user.setPasswordHash(passwordEncoder.encode(password));
        user.setRole("user");
        userRepository.insert(user);

        StpUtil.login(user.getUserId());
        String token = StpUtil.getTokenValue();

        Map<String, Object> result = new HashMap<>();
        result.put("token", token);
        result.put("user_id", user.getUserId());
        result.put("role", user.getRole());
        return result;
    }

    @Override
    public void logout(String token) {
        StpUtil.logout();
    }
}
