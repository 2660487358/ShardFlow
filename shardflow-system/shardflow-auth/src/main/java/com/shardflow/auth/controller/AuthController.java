package com.shardflow.auth.controller;

import com.shardflow.auth.repository.UserRepository;
import com.shardflow.auth.service.JwtService;
import com.shardflow.common.entity.UserEntity;
import org.springframework.http.ResponseEntity;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/auth")
public class AuthController {

    private final JwtService jwtService;
    private final UserRepository userRepository;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder(12);

    public AuthController(JwtService jwtService, UserRepository userRepository) {
        this.jwtService = jwtService;
        this.userRepository = userRepository;
    }

    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        String username = body.get("username");
        String password = body.get("password");

        UserEntity user = userRepository.findByUsername(username)
            .orElse(null);

        if (user == null || !passwordEncoder.matches(password, user.getPasswordHash())) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid credentials"));
        }

        String token = jwtService.generateAccessToken(username, user.getUserId(), user.getRole());
        String refreshToken = jwtService.generateRefreshToken(user.getUserId());

        return ResponseEntity.ok(Map.of(
            "token", token,
            "refresh_token", refreshToken,
            "expires_in", jwtService.getAccessExpirationSeconds()
        ));
    }

    @PostMapping("/refresh")
    public ResponseEntity<Map<String, Object>> refresh(@RequestBody Map<String, String> body) {
        try {
            String newToken = jwtService.refreshAccessToken(body.get("refresh_token"));
            return ResponseEntity.ok(Map.of(
                "token", newToken,
                "expires_in", jwtService.getAccessExpirationSeconds()
            ));
        } catch (Exception e) {
            return ResponseEntity.status(401).body(Map.of("error", "Invalid refresh token"));
        }
    }

    @PostMapping("/logout")
    public ResponseEntity<Map<String, Object>> logout(@RequestHeader("Authorization") String authHeader) {
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            jwtService.logout(authHeader.substring(7));
        }
        return ResponseEntity.ok(Map.of("status", "ok"));
    }
}
