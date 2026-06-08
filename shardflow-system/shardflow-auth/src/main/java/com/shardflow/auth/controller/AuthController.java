package com.shardflow.auth.controller;

import com.shardflow.auth.service.AuthService;
import com.shardflow.common.dto.Result;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @PostMapping("/login")
    public Result<Map<String, Object>> login(@RequestBody Map<String, String> body) {
        return Result.ok(authService.login(body.get("username"), body.get("password")));
    }

    @PostMapping("/register")
    public Result<Map<String, Object>> register(@RequestBody Map<String, String> body) {
        return Result.ok(authService.register(body.get("username"), body.get("password")));
    }

    @PostMapping("/refresh")
    public Result<Map<String, Object>> refresh(@RequestBody Map<String, String> body) {
        return Result.ok(authService.refresh(body.get("refresh_token")));
    }

    @PostMapping("/logout")
    public Result<Void> logout(@RequestHeader("Authorization") String authHeader,
                               @RequestBody(required = false) Map<String, String> body) {
        String token = null;
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            token = authHeader.substring(7);
        }
        String refreshToken = body != null ? body.get("refresh_token") : null;
        authService.logout(token, refreshToken);
        return Result.ok();
    }
}
