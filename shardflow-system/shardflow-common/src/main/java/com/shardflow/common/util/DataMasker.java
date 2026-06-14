package com.shardflow.common.util;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 数据脱敏工具 (SEC-DATA-001, SEC-DATA-002).
 *
 * <p>提供敏感字段掩码和审计日志脱敏功能：
 * <ul>
 *   <li>手机号：保留前3后4，中间掩码</li>
 *   <li>邮箱：保留首字符和@后域名，中间掩码</li>
 *   <li>身份证：保留前3后4，中间掩码</li>
 *   <li>银行卡：保留前4后4，中间掩码</li>
 * </ul>
 */
public final class DataMasker {

    private static final Pattern PHONE_PATTERN = Pattern.compile("1[3-9]\\d{9}");
    private static final Pattern EMAIL_PATTERN = Pattern.compile("([a-zA-Z0-9._%+-])[^@]*@([a-zA-Z0-9.-]+\\.[a-zA-Z]{2,})");
    private static final Pattern ID_CARD_PATTERN = Pattern.compile("\\d{17}[\\dXx]");
    private static final Pattern BANK_CARD_PATTERN = Pattern.compile("\\d{4}\\s*\\d{4,}\\s*\\d{4,}\\s*\\d{0,4}");

    private DataMasker() {}

    /**
     * 对文本中的敏感字段进行掩码处理 (SEC-DATA-002).
     */
    public static String maskSensitiveFields(String text) {
        if (text == null || text.isBlank()) {
            return text;
        }
        String result = text;
        result = PHONE_PATTERN.matcher(result).replaceAll(m -> m.group(0).substring(0, 3) + "****" + m.group(0).substring(7));
        result = EMAIL_PATTERN.matcher(result).replaceAll(m -> m.group(1) + "***@" + m.group(2));
        result = ID_CARD_PATTERN.matcher(result).replaceAll(m -> m.group(0).substring(0, 3) + "***********" + m.group(0).substring(14));
        result = BANK_CARD_PATTERN.matcher(result).replaceAll(DataMasker::maskBankCard);
        return result;
    }

    private static String maskBankCard(java.util.regex.MatchResult m) {
        String digits = m.group(0).replaceAll("\\s", "");
        if (digits.length() < 8) return "****";
        return digits.substring(0, 4) + " **** **** " + digits.substring(digits.length() - 4);
    }

    /**
     * 对审计日志输入参数进行脱敏 (SEC-DATA-001).
     * 截断至 1KB 并掩码敏感字段。
     */
    public static String maskAuditInput(String input) {
        if (input == null) return null;
        String masked = maskSensitiveFields(input);
        return truncate(masked, 1024);
    }

    /**
     * 对审计日志输出预览进行脱敏 (SEC-DATA-001).
     * 截断至 1KB 并掩码敏感字段。
     */
    public static String maskAuditOutput(String output) {
        if (output == null) return null;
        String masked = maskSensitiveFields(output);
        return truncate(masked, 1024);
    }

    /**
     * 对 JSON Map 中的敏感值进行脱敏.
     * 对 auth_config 等字段仅保留 type，移除密钥值。
     */
    public static Map<String, Object> maskAuthConfig(Map<String, Object> authConfig) {
        if (authConfig == null) return null;
        Map<String, Object> masked = new LinkedHashMap<>();
        Object type = authConfig.get("type");
        masked.put("type", type != null ? type : "unknown");
        return masked;
    }

    private static String truncate(String text, int maxLen) {
        if (text.length() <= maxLen) return text;
        return text.substring(0, maxLen) + "...[truncated]";
    }
}
