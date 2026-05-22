package com.shardflow.auth.service;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.Map;
import java.util.UUID;

@Service
public class JwtService {

    private static final long ACCESS_EXPIRATION_SECONDS = 7200;
    private static final long REFRESH_EXPIRATION_SECONDS = 604800;

    private final SecretKey key;
    private final RedisTemplate<String, Object> redisTemplate;

    public JwtService(@Value("${shardflow.jwt.secret:shardflow-jwt-secret-key-must-be-at-least-256-bits-long!!}") String secret,
                      RedisTemplate<String, Object> redisTemplate) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.redisTemplate = redisTemplate;
    }

    public String generateAccessToken(String username, String userId, String role) {
        Instant now = Instant.now();
        return Jwts.builder()
            .id(UUID.randomUUID().toString())
            .subject(username)
            .claims(Map.of("user_id", userId, "role", role))
            .issuedAt(Date.from(now))
            .expiration(Date.from(now.plusSeconds(ACCESS_EXPIRATION_SECONDS)))
            .signWith(key)
            .compact();
    }

    public String generateRefreshToken(String userId) {
        String token = UUID.randomUUID().toString();
        redisTemplate.opsForValue().set(
            "shardflow:refresh:" + token, userId,
            Duration.ofSeconds(REFRESH_EXPIRATION_SECONDS)
        );
        return token;
    }

    public Map<String, Object> validateToken(String token) {
        var claims = Jwts.parser().verifyWith(key).build()
            .parseSignedClaims(token).getPayload();

        String jti = claims.getId();
        if (Boolean.TRUE.equals(redisTemplate.hasKey("shardflow:blacklist:" + jti))) {
            throw new RuntimeException("Token has been revoked");
        }

        return Map.of(
            "username", claims.getSubject(),
            "user_id", String.valueOf(claims.get("user_id", "")),
            "role", String.valueOf(claims.get("role", "")),
            "jti", jti
        );
    }

    public String refreshAccessToken(String refreshToken) {
        String userId = (String) redisTemplate.opsForValue().get("shardflow:refresh:" + refreshToken);
        if (userId == null) {
            throw new RuntimeException("Invalid or expired refresh token");
        }
        redisTemplate.delete("shardflow:refresh:" + refreshToken);
        return generateAccessToken(userId, userId, "USER");
    }

    public void logout(String token) {
        try {
            var claims = Jwts.parser().verifyWith(key).build()
                .parseSignedClaims(token).getPayload();
            String jti = claims.getId();
            long remaining = claims.getExpiration().getTime() - System.currentTimeMillis();
            if (remaining > 0) {
                redisTemplate.opsForValue().set(
                    "shardflow:blacklist:" + jti, "1",
                    Duration.ofMillis(remaining)
                );
            }
        } catch (Exception ignored) {
            // Token already invalid, nothing to blacklist
        }
    }

    public long getAccessExpirationSeconds() {
        return ACCESS_EXPIRATION_SECONDS;
    }
}
