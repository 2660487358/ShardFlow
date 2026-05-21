package com.shardflow.auth.controller;

import com.shardflow.auth.service.JwtService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final JwtService jwtService;

    public AuthController(JwtService jwtService) { this.jwtService = jwtService; }

    @PostMapping("/login")
    public ResponseEntity<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        String username = body.get("username");
        String password = body.get("password");
        // In production: validate against DB
        if ("admin".equals(username) && "admin".equals(password)) {
            String token = jwtService.generateToken(username, "admin-tenant", "ADMIN");
            return ResponseEntity.ok(Map.of("token", token, "username", username));
        }
        return ResponseEntity.status(401).body(Map.of("error", "Invalid credentials"));
    }

    @PostMapping("/register")
    public ResponseEntity<Map<String, Object>> register(@RequestBody Map<String, String> body) {
        return ResponseEntity.ok(Map.of("status", "ok", "message", "User registered"));
    }
}
