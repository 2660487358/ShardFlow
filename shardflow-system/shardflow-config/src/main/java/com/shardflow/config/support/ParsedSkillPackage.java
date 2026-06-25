package com.shardflow.config.support;

import com.shardflow.config.dto.SkillImportRequest;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 压缩包解析结果模型.
 *
 * <p>由 {@link SkillPackageParser} 解析压缩包后产生，包含：
 * <ul>
 *   <li>metadata — Skill 元数据（从 skill.json 或 SKILL.md frontmatter 解析）</li>
 *   <li>manifestJson — manifest.json 原始内容（可选，存在时用于 Artifact 识别）</li>
 *   <li>artifacts — 文件名 → 文件内容映射（待上传到 MinIO 的 Artifact 文件）</li>
 *   <li>sourceType — 来源类型：json | zip | targz</li>
 *   <li>version — 版本号（从 skill.json 读取，默认 1.0.0）</li>
 * </ul>
 */
@Data
@NoArgsConstructor
public class ParsedSkillPackage {

    /** Skill 元数据（从 skill.json 或 SKILL.md frontmatter 解析） */
    private SkillImportRequest metadata;

    /** manifest.json 原始内容（可选） */
    private String manifestJson;

    /** 待上传的 Artifact 文件：文件名 → 文件内容 */
    private Map<String, byte[]> artifacts = new LinkedHashMap<>();

    /** 来源类型：json | zip | targz */
    private String sourceType;

    /** 版本号（从 skill.json 读取，默认 1.0.0） */
    private String version = "1.0.0";

    /** 压缩包文件名（用于回退推导 skill_name） */
    private String packageFileName;
}
