package com.shardflow.auth.service;

import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.stereotype.Service;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;

@Service
public class JwtService {

    private static final String SECRET = "shardflow-jwt-secret-key-must-be-at-least-256-bits-long!!";
    private static final long EXPIRATION_HOURS = 24;

    public String generateToken(String username, String tenantId, String role) {
        SecretKey key = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));
        Instant now = Instant.now();
        return Jwts.builder()
            .subject(username)
            .claims(Map.of("tenant_id", tenantId, "role", role))
            .issuedAt(Date.from(now))
            .expiration(Date.from(now.plusSeconds(EXPIRATION_HOURS * 3600)))
            .signWith(key)
            .compact();
    }

    public Map<String, String> validateToken(String token) {
        SecretKey key = Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));
        var claims = Jwts.parser().verifyWith(key).build()
            .parseSignedClaims(token).getPayload();
        return Map.of(
            "username", claims.getSubject(),
            "tenant_id", String.valueOf(claims.get("tenant_id", "")),
            "role", String.valueOf(claims.get("role", ""))
        );
    }
}
