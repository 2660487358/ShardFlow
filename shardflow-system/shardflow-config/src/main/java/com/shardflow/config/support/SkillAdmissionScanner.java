package com.shardflow.config.support;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Skill 准入扫描器.
 *
 * <p>Per Skills管理需求规格文档 FR-8.1 / NFR-5.5~5.9 / 实施计划 P6.1.
 * <p>在 Skill 发布前执行安全扫描，检测：
 * <ul>
 *   <li>Prompt 注入检测（正则 + 关键词）</li>
 *   <li>敏感信息泄露（密钥/密码/内网地址）</li>
 *   <li>代码静态分析（危险 import / 危险内置函数）</li>
 *   <li>依赖审计（requirements.txt 版本检查）</li>
 * </ul>
 *
 * <p>扫描未通过返回 SKILL_ADMISSION_REJECTED 及具体问题列表。
 * <p>V1 简化版：基于正则与关键词匹配；V2 阶段引入 LLM 语义分析与 bandit/semgrep。
 */
@Slf4j
@Component
public class SkillAdmissionScanner {

    /** 扫描问题严重级别 */
    public static final String SEVERITY_CRITICAL = "CRITICAL";
    public static final String SEVERITY_HIGH = "HIGH";
    public static final String SEVERITY_MEDIUM = "MEDIUM";
    public static final String SEVERITY_LOW = "LOW";

    // ── Prompt 注入检测正则 ──
    private static final Pattern[] PROMPT_INJECTION_PATTERNS = {
        // 忽略之前所有指令
        Pattern.compile("(?i)ignore\\s+(?:all\\s+)?(?:previous|prior|above)\\s+instructions"),
        // 系统提示泄露
        Pattern.compile("(?i)(?:reveal|show|print|output)\\s+(?:your\\s+)?system\\s+prompt"),
        // 角色越权
        Pattern.compile("(?i)(?:you\\s+are|act\\s+as|pretend\\s+to\\s+be)\\s+(?:root|admin|developer|dan)"),
        // 指令覆盖
        Pattern.compile("(?i)(?:disregard|forget|override)\\s+(?:all\\s+)?(?:previous|prior)"),
        // 越狱关键词
        Pattern.compile("(?i)(?:jailbreak|do\\s+anything\\s+now|DAN)"),
    };

    // ── 敏感信息泄露检测正则 ──
    private static final Pattern[] SENSITIVE_INFO_PATTERNS = {
        // AWS Access Key
        Pattern.compile("AKIA[0-9A-Z]{16}"),
        // AWS Secret Key
        Pattern.compile("(?i)aws_secret_access_key\\s*[=:]\\s*[A-Za-z0-9/+=]{40}"),
        // OpenAI API Key
        Pattern.compile("sk-[A-Za-z0-9]{48}"),
        // 通用密码模式
        Pattern.compile("(?i)(?:password|passwd|pwd)\\s*[=:]\\s*['\"][^'\"]{8,}['\"]"),
        // 数据库连接字符串
        Pattern.compile("(?i)(?:mongodb|postgres|mysql|redis)://[^\\s]+:[^\\s]+@"),
        // 私钥
        Pattern.compile("-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
        // 内网 IP 地址
        Pattern.compile("\\b(?:10\\.|172\\.(?:1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.)\\d{1,3}\\.\\d{1,3}\\b"),
    };

    // ── 代码静态分析：危险 import ──
    private static final String[] DANGEROUS_IMPORTS = {
        "import os", "import sys", "import subprocess", "import shutil",
        "import ctypes", "import multiprocessing", "import socket",
        "from os ", "from sys ", "from subprocess ",
    };

    // ── 代码静态分析：危险内置函数 ──
    private static final Pattern[] DANGEROUS_BUILTIN_PATTERNS = {
        Pattern.compile("\\bexec\\s*\\("),
        Pattern.compile("\\beval\\s*\\("),
        Pattern.compile("\\bcompile\\s*\\("),
        Pattern.compile("\\b__import__\\s*\\("),
        Pattern.compile("\\bopen\\s*\\("),
    };

    // ── 已知漏洞依赖版本（V1 简化示例，V2 接入 OSV/Snyk 数据库）──
    private static final String[] VULNERABLE_DEPENDENCIES = {
        "requests==2.25.0", "urllib3==1.26.0", "jinja2==3.0.0",
        "flask==1.1.0", "django==3.1.0", "cryptography==3.3.0",
    };

    /**
     * 扫描 Skill 内容.
     *
     * @param skillName    Skill 名称
     * @param description  Skill 描述
     * @param promptContent prompt.md 内容（可为 null）
     * @param toolCode     tool.py 内容（可为 null）
     * @param requirements requirements.txt 内容（可为 null）
     * @return 扫描结果
     */
    public ScanResult scan(
            String skillName,
            String description,
            String promptContent,
            String toolCode,
            String requirements
    ) {
        List<ScanIssue> issues = new ArrayList<>();

        // 1. Prompt 注入检测
        if (promptContent != null && !promptContent.isEmpty()) {
            issues.addAll(scanPromptInjection(skillName, promptContent));
        }
        if (description != null && !description.isEmpty()) {
            issues.addAll(scanPromptInjection(skillName, description));
        }

        // 2. 敏感信息泄露检测
        if (promptContent != null && !promptContent.isEmpty()) {
            issues.addAll(scanSensitiveInfo(skillName, promptContent));
        }
        if (toolCode != null && !toolCode.isEmpty()) {
            issues.addAll(scanSensitiveInfo(skillName, toolCode));
        }

        // 3. 代码静态分析
        if (toolCode != null && !toolCode.isEmpty()) {
            issues.addAll(scanCodeStatic(skillName, toolCode));
        }

        // 4. 依赖审计
        if (requirements != null && !requirements.isEmpty()) {
            issues.addAll(scanDependencies(skillName, requirements));
        }

        boolean passed = issues.stream()
                .noneMatch(i -> SEVERITY_CRITICAL.equals(i.severity) || SEVERITY_HIGH.equals(i.severity));

        log.info("SkillAdmissionScanner: skill={} issues={} passed={}",
                skillName, issues.size(), passed);

        return new ScanResult(passed, issues);
    }

    // ── Prompt 注入检测 ──

    private List<ScanIssue> scanPromptInjection(String skillName, String content) {
        List<ScanIssue> issues = new ArrayList<>();
        for (Pattern pattern : PROMPT_INJECTION_PATTERNS) {
            var matcher = pattern.matcher(content);
            if (matcher.find()) {
                issues.add(new ScanIssue(
                        SEVERITY_CRITICAL,
                        "PROMPT_INJECTION",
                        "检测到 Prompt 注入风险: " + matcher.group(),
                        skillName
                ));
            }
        }
        return issues;
    }

    // ── 敏感信息泄露检测 ──

    private List<ScanIssue> scanSensitiveInfo(String skillName, String content) {
        List<ScanIssue> issues = new ArrayList<>();
        for (Pattern pattern : SENSITIVE_INFO_PATTERNS) {
            var matcher = pattern.matcher(content);
            if (matcher.find()) {
                issues.add(new ScanIssue(
                        SEVERITY_CRITICAL,
                        "SENSITIVE_INFO_LEAK",
                        "检测到敏感信息泄露: " + matcher.group().substring(0, Math.min(50, matcher.group().length())),
                        skillName
                ));
            }
        }
        return issues;
    }

    // ── 代码静态分析 ──

    private List<ScanIssue> scanCodeStatic(String skillName, String code) {
        List<ScanIssue> issues = new ArrayList<>();

        // 危险 import
        for (String dangerousImport : DANGEROUS_IMPORTS) {
            if (code.contains(dangerousImport)) {
                issues.add(new ScanIssue(
                        SEVERITY_HIGH,
                        "DANGEROUS_IMPORT",
                        "检测到危险导入: " + dangerousImport,
                        skillName
                ));
            }
        }

        // 危险内置函数
        for (Pattern pattern : DANGEROUS_BUILTIN_PATTERNS) {
            var matcher = pattern.matcher(code);
            if (matcher.find()) {
                issues.add(new ScanIssue(
                        SEVERITY_HIGH,
                        "DANGEROUS_BUILTIN",
                        "检测到危险内置函数调用: " + matcher.group(),
                        skillName
                ));
            }
        }

        return issues;
    }

    // ── 依赖审计 ──

    private List<ScanIssue> scanDependencies(String skillName, String requirements) {
        List<ScanIssue> issues = new ArrayList<>();
        String[] lines = requirements.split("\\r?\\n");
        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.isEmpty() || trimmed.startsWith("#")) {
                continue;
            }
            for (String vuln : VULNERABLE_DEPENDENCIES) {
                if (trimmed.toLowerCase().contains(vuln.toLowerCase())) {
                    issues.add(new ScanIssue(
                            SEVERITY_MEDIUM,
                            "VULNERABLE_DEPENDENCY",
                            "检测到已知漏洞依赖: " + trimmed,
                            skillName
                    ));
                }
            }
        }
        return issues;
    }

    // ── 扫描结果数据结构 ──

    public record ScanResult(boolean passed, List<ScanIssue> issues) {}

    public record ScanIssue(String severity, String type, String message, String skillName) {}
}
