package com.shardflow.config.support;

import com.shardflow.config.dto.SkillImportRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * Skill 压缩包解析工具类.
 *
 * <p>支持三种导入格式：
 * <ul>
 *   <li>JSON 文件（单对象或数组）— 兼容原有导入方式</li>
 *   <li>ZIP 压缩包 — 支持 .zip 格式</li>
 *   <li>TAR.GZ 压缩包 — 支持 .tar.gz / .tgz 格式</li>
 * </ul>
 *
 * <p>支持三种 Skill 包形态：
 * <ul>
 *   <li>极简型 — 仅一个 SKILL.md（含 YAML frontmatter）</li>
 *   <li>标准型 — skill.json + 工件文件（无 manifest.json）</li>
 *   <li>完整型 — skill.json + manifest.json + 工件文件</li>
 * </ul>
 *
 * <p>安全防护：Zip Slip 路径穿越攻击防护，解压路径禁止包含 ".." 和绝对路径。
 */
@Slf4j
@Component
public class SkillPackageParser {

    private final ObjectMapper objectMapper;

    /** 压缩包最大解压后总大小（100MB） */
    private static final long MAX_TOTAL_EXTRACTED_SIZE = 100 * 1024 * 1024L;

    /** 单个文件最大大小（50MB） */
    private static final long MAX_SINGLE_FILE_SIZE = 50 * 1024 * 1024L;

    /** YAML frontmatter 正则：--- 开头，--- 结束 */
    private static final Pattern FRONTMATTER_PATTERN =
        Pattern.compile("^---\\s*\\n(.*?)\\n---\\s*\\n", Pattern.DOTALL);

    /** YAML 字段提取正则 */
    private static final Pattern YAML_FIELD_PATTERN =
        Pattern.compile("^(\\w+):\\s*(.+?)\\s*$", Pattern.MULTILINE);

    public SkillPackageParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * 解析上传的 Skill 文件（JSON / ZIP / TAR.GZ）.
     *
     * @param file 上传的文件
     * @return 解析结果（可能包含多个 Skill 包，JSON 数组时返回多个）
     * @throws IOException 文件读取或解析失败
     */
    public ParsedSkillPackage parse(MultipartFile file) throws IOException {
        String filename = file.getOriginalFilename();
        if (filename == null) {
            filename = "";
        }
        String lowerName = filename.toLowerCase();

        if (lowerName.endsWith(".zip")) {
            return parseZip(file.getBytes(), filename);
        } else if (lowerName.endsWith(".tar.gz") || lowerName.endsWith(".tgz")) {
            return parseTarGz(file.getBytes(), filename);
        } else if (lowerName.endsWith(".json")) {
            return parseJson(file.getBytes(), filename);
        } else {
            throw new IllegalArgumentException(
                "不支持的文件格式: " + filename + "，支持 .json / .zip / .tar.gz / .tgz");
        }
    }

    /**
     * 判断是否为压缩包格式.
     */
    public static boolean isArchiveFormat(String filename) {
        if (filename == null) return false;
        String lower = filename.toLowerCase();
        return lower.endsWith(".zip") || lower.endsWith(".tar.gz") || lower.endsWith(".tgz");
    }

    // ======================== ZIP 解析 ========================

    private ParsedSkillPackage parseZip(byte[] data, String packageFileName) throws IOException {
        Map<String, byte[]> files = new LinkedHashMap<>();
        long totalSize = 0;

        try (ZipInputStream zis = new ZipInputStream(new ByteArrayInputStream(data))) {
            ZipEntry entry;
            while ((entry = zis.getNextEntry()) != null) {
                if (entry.isDirectory()) continue;

                String entryName = entry.getName();

                // Zip Slip 防护：禁止路径穿越
                if (entryName.contains("..") || entryName.startsWith("/") || entryName.startsWith("\\")) {
                    throw new IllegalArgumentException("压缩包包含不安全的路径: " + entryName);
                }

                // 读取文件内容
                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int len;
                while ((len = zis.read(buffer)) > 0) {
                    baos.write(buffer, 0, len);
                    totalSize += len;
                    if (totalSize > MAX_TOTAL_EXTRACTED_SIZE) {
                        throw new IllegalArgumentException("压缩包解压后总大小超过 100MB 限制");
                    }
                }

                byte[] content = baos.toByteArray();
                if (content.length > MAX_SINGLE_FILE_SIZE) {
                    throw new IllegalArgumentException("单个文件大小超过 50MB 限制: " + entryName);
                }

                files.put(entryName, content);
            }
        }

        if (files.isEmpty()) {
            throw new IllegalArgumentException("压缩包为空");
        }

        // 规范化文件路径（处理单层目录布局）
        Map<String, byte[]> normalizedFiles = normalizePaths(files);

        return buildPackage(normalizedFiles, packageFileName, "zip");
    }

    // ======================== TAR.GZ 解析 ========================

    private ParsedSkillPackage parseTarGz(byte[] data, String packageFileName) throws IOException {
        // 使用 commons-compress 解析 TAR.GZ
        Map<String, byte[]> files = new LinkedHashMap<>();
        long totalSize = 0;

        try (InputStream fis = new ByteArrayInputStream(data);
             InputStream gis = new java.util.zip.GZIPInputStream(fis);
             org.apache.commons.compress.archivers.tar.TarArchiveInputStream tis =
                 new org.apache.commons.compress.archivers.tar.TarArchiveInputStream(gis)) {

            org.apache.commons.compress.archivers.tar.TarArchiveEntry entry;
            while ((entry = tis.getNextTarEntry()) != null) {
                if (entry.isDirectory()) continue;

                String entryName = entry.getName();

                // Zip Slip 防护
                if (entryName.contains("..") || entryName.startsWith("/") || entryName.startsWith("\\")) {
                    throw new IllegalArgumentException("压缩包包含不安全的路径: " + entryName);
                }

                ByteArrayOutputStream baos = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int len;
                while ((len = tis.read(buffer)) > 0) {
                    baos.write(buffer, 0, len);
                    totalSize += len;
                    if (totalSize > MAX_TOTAL_EXTRACTED_SIZE) {
                        throw new IllegalArgumentException("压缩包解压后总大小超过 100MB 限制");
                    }
                }

                byte[] content = baos.toByteArray();
                if (content.length > MAX_SINGLE_FILE_SIZE) {
                    throw new IllegalArgumentException("单个文件大小超过 50MB 限制: " + entryName);
                }

                files.put(entryName, content);
            }
        }

        if (files.isEmpty()) {
            throw new IllegalArgumentException("压缩包为空");
        }

        Map<String, byte[]> normalizedFiles = normalizePaths(files);
        return buildPackage(normalizedFiles, packageFileName, "targz");
    }

    // ======================== JSON 解析 ========================

    private ParsedSkillPackage parseJson(byte[] data, String packageFileName) throws IOException {
        String json = new String(data, StandardCharsets.UTF_8).trim();
        ParsedSkillPackage pkg = new ParsedSkillPackage();
        pkg.setSourceType("json");
        pkg.setPackageFileName(packageFileName);

        try {
            SkillImportRequest metadata = objectMapper.readValue(json, SkillImportRequest.class);
            pkg.setMetadata(metadata);
        } catch (Exception e) {
            throw new IllegalArgumentException("JSON 格式无效: " + e.getMessage());
        }

        return pkg;
    }

    // ======================== 构建解析结果 ========================

    /**
     * 从解压后的文件列表构建 ParsedSkillPackage.
     */
    private ParsedSkillPackage buildPackage(Map<String, byte[]> files, String packageFileName, String sourceType) {
        ParsedSkillPackage pkg = new ParsedSkillPackage();
        pkg.setSourceType(sourceType);
        pkg.setPackageFileName(packageFileName);

        // 1. 解析元数据（优先级：skill.json > SKILL.md frontmatter > 文件名回退）
        SkillImportRequest metadata = parseMetadata(files, packageFileName);
        pkg.setMetadata(metadata);

        // 2. 解析 manifest.json（可选）
        String manifestJson = findFileContent(files, "manifest.json");
        if (manifestJson != null) {
            pkg.setManifestJson(manifestJson);
        }

        // 3. 识别 Artifact 文件
        Map<String, byte[]> artifacts = identifyArtifacts(files, manifestJson);
        pkg.setArtifacts(artifacts);

        // 4. 提取版本号
        String version = extractVersion(files, metadata);
        pkg.setVersion(version);

        return pkg;
    }

    /**
     * 解析 Skill 元数据.
     * 优先级 1: skill.json
     * 优先级 2: SKILL.md / skill.md 的 YAML frontmatter
     * 优先级 3: 压缩包文件名回退
     */
    private SkillImportRequest parseMetadata(Map<String, byte[]> files, String packageFileName) {
        // 优先级 1: skill.json
        String skillJsonContent = findFileContent(files, "skill.json");
        if (skillJsonContent != null) {
            try {
                SkillImportRequest metadata = objectMapper.readValue(skillJsonContent, SkillImportRequest.class);
                log.debug("Parsed metadata from skill.json");
                return metadata;
            } catch (Exception e) {
                log.warn("Failed to parse skill.json: {}", e.getMessage());
                // 继续尝试其他来源
            }
        }

        // 优先级 2: SKILL.md / skill.md 的 YAML frontmatter
        String mdContent = findFileContent(files, "SKILL.md");
        if (mdContent == null) {
            mdContent = findFileContent(files, "skill.md");
        }
        if (mdContent != null) {
            SkillImportRequest metadata = parseFromFrontmatter(mdContent);
            if (metadata != null) {
                log.debug("Parsed metadata from SKILL.md frontmatter");
                return metadata;
            }
        }

        // 优先级 3: 文件名回退
        SkillImportRequest metadata = new SkillImportRequest();
        String baseName = packageFileName;
        int dotIdx = baseName.lastIndexOf('.');
        if (dotIdx > 0) {
            baseName = baseName.substring(0, dotIdx);
        }
        metadata.setSkillName(baseName);
        metadata.setSkillType("prompt");
        metadata.setTrustTier("personal");
        metadata.setDescription("");
        log.debug("Fallback to package filename as skill_name: {}", baseName);
        return metadata;
    }

    /**
     * 从 Markdown YAML frontmatter 解析元数据.
     * 格式：
     * ---
     * name: skill-name
     * description: Use when ...
     * ---
     */
    private SkillImportRequest parseFromFrontmatter(String mdContent) {
        Matcher fmMatcher = FRONTMATTER_PATTERN.matcher(mdContent);
        if (!fmMatcher.find()) {
            return null;
        }

        String frontmatter = fmMatcher.group(1);
        SkillImportRequest metadata = new SkillImportRequest();
        metadata.setSkillType("prompt");
        metadata.setTrustTier("personal");

        Matcher fieldMatcher = YAML_FIELD_PATTERN.matcher(frontmatter);
        boolean hasName = false;
        while (fieldMatcher.find()) {
            String key = fieldMatcher.group(1).trim();
            String value = fieldMatcher.group(2).trim();
            // 移除引号
            if ((value.startsWith("\"") && value.endsWith("\"")) ||
                (value.startsWith("'") && value.endsWith("'"))) {
                value = value.substring(1, value.length() - 1);
            }

            switch (key) {
                case "name":
                    metadata.setSkillName(value);
                    hasName = true;
                    break;
                case "description":
                    metadata.setDescription(value);
                    break;
                case "skill_type":
                    metadata.setSkillType(value);
                    break;
                case "trust_tier":
                    metadata.setTrustTier(value);
                    break;
            }
        }

        if (!hasName) {
            return null;
        }
        return metadata;
    }

    /**
     * 识别 Artifact 文件.
     * manifest.json 存在时按 manifest.artifacts 列表识别，否则按文件名自动识别。
     */
    private Map<String, byte[]> identifyArtifacts(Map<String, byte[]> files, String manifestJson) {
        Map<String, byte[]> artifacts = new LinkedHashMap<>();

        if (manifestJson != null) {
            // 按 manifest.artifacts 列表识别
            try {
                JsonNode manifest = objectMapper.readTree(manifestJson);
                JsonNode artifactsNode = manifest.path("artifacts");
                if (artifactsNode.isArray()) {
                    for (JsonNode item : artifactsNode) {
                        String fileName = item.path("file").asText("");
                        if (!fileName.isEmpty() && files.containsKey(fileName)) {
                            artifacts.put(fileName, files.get(fileName));
                        }
                    }
                    if (!artifacts.isEmpty()) {
                        return artifacts;
                    }
                }
            } catch (Exception e) {
                log.warn("Failed to parse manifest.json artifacts: {}", e.getMessage());
            }
        }

        // 按文件名自动识别
        for (Map.Entry<String, byte[]> entry : files.entrySet()) {
            String fileName = entry.getKey();
            String lowerName = fileName.toLowerCase();

            if (lowerName.equals("skill.json") || lowerName.equals("manifest.json")) {
                artifacts.put(fileName, entry.getValue());
            } else if (lowerName.equals("skill.md") || lowerName.equals("prompt.md")) {
                artifacts.put(fileName, entry.getValue());
            } else if (lowerName.equals("tool.py")) {
                artifacts.put(fileName, entry.getValue());
            } else if (lowerName.equals("workflow.yaml") || lowerName.equals("workflow.yml")) {
                artifacts.put(fileName, entry.getValue());
            }
            // 其他文件跳过
        }

        return artifacts;
    }

    /**
     * 提取版本号（从 skill.json 的 version 字段，默认 1.0.0）.
     */
    private String extractVersion(Map<String, byte[]> files, SkillImportRequest metadata) {
        String skillJsonContent = findFileContent(files, "skill.json");
        if (skillJsonContent != null) {
            try {
                JsonNode node = objectMapper.readTree(skillJsonContent);
                String version = node.path("version").asText("");
                if (!version.isEmpty()) {
                    return version;
                }
            } catch (Exception e) {
                // 忽略，使用默认值
            }
        }
        return "1.0.0";
    }

    // ======================== 辅助方法 ========================

    /**
     * 规范化文件路径，处理单层目录布局.
     * 如果所有文件都在同一个子目录下，则去掉该目录前缀。
     */
    private Map<String, byte[]> normalizePaths(Map<String, byte[]> files) {
        // 检查是否所有文件都在同一个子目录下
        String commonDir = null;
        for (String path : files.keySet()) {
            int slashIdx = path.indexOf('/');
            if (slashIdx <= 0) {
                // 有文件在根目录，无需规范化
                return files;
            }
            String dir = path.substring(0, slashIdx);
            if (commonDir == null) {
                commonDir = dir;
            } else if (!commonDir.equals(dir)) {
                // 多个不同目录，不规范化
                return files;
            }
        }

        if (commonDir != null) {
            // 去掉公共目录前缀
            Map<String, byte[]> normalized = new LinkedHashMap<>();
            String prefix = commonDir + "/";
            for (Map.Entry<String, byte[]> entry : files.entrySet()) {
                String newPath = entry.getKey().substring(prefix.length());
                normalized.put(newPath, entry.getValue());
            }
            return normalized;
        }

        return files;
    }

    /**
     * 查找文件内容（不区分大小写）.
     *
     * @return 文件内容字符串，不存在返回 null
     */
    private String findFileContent(Map<String, byte[]> files, String targetName) {
        String lowerTarget = targetName.toLowerCase();
        for (Map.Entry<String, byte[]> entry : files.entrySet()) {
            if (entry.getKey().toLowerCase().equals(lowerTarget)) {
                return new String(entry.getValue(), StandardCharsets.UTF_8);
            }
        }
        return null;
    }
}
