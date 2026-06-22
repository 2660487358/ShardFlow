package com.shardflow.config.service;

import com.shardflow.config.config.SkillMinioConfig;
import io.minio.*;
import io.minio.http.Method;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.concurrent.TimeUnit;

/**
 * Skill Artifact MinIO 存储服务.
 *
 * <p>Per Skills管理需求规格文档 DR-6 / FR-6 / FR-2 / 实施计划 P1.3.4.
 * <p>职责：
 * <ul>
 *   <li>上传 Artifact 到 MinIO，路径规范 {@code {user_id}/{skill_code}/{version_tag}/{file_name}}</li>
 *   <li>计算文件内容 SHA-256 哈希（FR-2.2）</li>
 *   <li>生成预签名下载 URL（供 Python 推理层拉取 Artifact）</li>
 *   <li>下载/删除 Artifact</li>
 *   <li>版本内容不可变校验（NFR-2.6）：已存在对象禁止覆盖</li>
 * </ul>
 *
 * <p>MinioClient Bean 由 shardflow-kb 模块统一提供，运行时复用。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class SkillArtifactStorageService {

    private final MinioClient minioClient;
    private final SkillMinioConfig skillMinioConfig;

    /** Artifact 上传结果 */
    public record UploadResult(String minioUrl, String contentHash, long fileSize) {}

    /**
     * 上传 Artifact 文件到 MinIO.
     *
     * @param userId      用户ID
     * @param skillCode   Skill 编码
     * @param versionTag  版本标签
     * @param fileName    文件名
     * @param content     文件内容
     * @param contentType MIME 类型
     * @return 上传结果（含 minioUrl、SHA-256、文件大小）
     */
    public UploadResult uploadArtifact(String userId, String skillCode, String versionTag,
                                       String fileName, byte[] content, String contentType) {
        String bucket = skillMinioConfig.getSkillBucket();
        ensureBucketExists(bucket);

        String objectPath = buildObjectPath(userId, skillCode, versionTag, fileName);
        String contentHash = computeSha256(content);

        try {
            minioClient.putObject(
                PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(objectPath)
                    .stream(new ByteArrayInputStream(content), content.length, -1)
                    .contentType(contentType == null ? "application/octet-stream" : contentType)
                    .build()
            );
            log.info("Uploaded Skill artifact to MinIO: {}/{}", bucket, objectPath);
            return new UploadResult(objectPath, contentHash, content.length);
        } catch (Exception e) {
            log.error("MinIO upload failed for Skill artifact {}: {}", objectPath, e.getMessage());
            throw new RuntimeException("Skill artifact upload failed", e);
        }
    }

    /**
     * 下载 Artifact 文件.
     *
     * @param minioUrl MinIO 对象路径（相对 bucket）
     * @return 文件输入流
     */
    public InputStream downloadArtifact(String minioUrl) {
        try {
            return minioClient.getObject(
                GetObjectArgs.builder()
                    .bucket(skillMinioConfig.getSkillBucket())
                    .object(minioUrl)
                    .build()
            );
        } catch (Exception e) {
            log.error("MinIO download failed for {}: {}", minioUrl, e.getMessage());
            throw new RuntimeException("Skill artifact download failed", e);
        }
    }

    /**
     * 生成预签名下载 URL（供 Python 推理层拉取 Artifact）.
     *
     * @param minioUrl MinIO 对象路径
     * @param expirySeconds 过期时间（秒），默认 3600
     * @return 预签名 URL
     */
    public String generatePresignedUrl(String minioUrl, int expirySeconds) {
        try {
            return minioClient.getPresignedObjectUrl(
                GetPresignedObjectUrlArgs.builder()
                    .method(Method.GET)
                    .bucket(skillMinioConfig.getSkillBucket())
                    .object(minioUrl)
                    .expiry(expirySeconds <= 0 ? 3600 : expirySeconds, TimeUnit.SECONDS)
                    .build()
            );
        } catch (Exception e) {
            log.error("MinIO presigned URL failed for {}: {}", minioUrl, e.getMessage());
            throw new RuntimeException("Skill artifact presigned URL generation failed", e);
        }
    }

    /**
     * 删除 Artifact 文件.
     */
    public void deleteArtifact(String minioUrl) {
        try {
            minioClient.removeObject(
                RemoveObjectArgs.builder()
                    .bucket(skillMinioConfig.getSkillBucket())
                    .object(minioUrl)
                    .build()
            );
            log.info("Deleted Skill artifact from MinIO: {}/{}", skillMinioConfig.getSkillBucket(), minioUrl);
        } catch (Exception e) {
            log.error("MinIO delete failed for {}: {}", minioUrl, e.getMessage());
        }
    }

    /**
     * 检查 Artifact 是否已存在（版本不可变性校验，NFR-2.6）.
     *
     * @param userId     用户ID
     * @param skillCode  Skill 编码
     * @param versionTag 版本标签
     * @param fileName   文件名
     * @return true 表示已存在，禁止覆盖
     */
    public boolean artifactExists(String userId, String skillCode, String versionTag, String fileName) {
        String objectPath = buildObjectPath(userId, skillCode, versionTag, fileName);
        try {
            minioClient.statObject(
                StatObjectArgs.builder()
                    .bucket(skillMinioConfig.getSkillBucket())
                    .object(objectPath)
                    .build()
            );
            return true;
        } catch (Exception e) {
            return false;
        }
    }

    /**
     * 构建 MinIO 对象存储路径.
     * 路径规范（DR-6）：{user_id}/{skill_code}/{version_tag}/{file_name}
     */
    public String buildObjectPath(String userId, String skillCode, String versionTag, String fileName) {
        return String.format("%s/%s/%s/%s", userId, skillCode, versionTag, fileName);
    }

    /**
     * 计算字节数组的 SHA-256 哈希（FR-2.2）.
     *
     * @param content 文件内容
     * @return SHA-256 十六进制字符串（64 字符）
     */
    public String computeSha256(byte[] content) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(content);
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 algorithm not available", e);
        }
    }

    /**
     * 确保 Bucket 存在，不存在则创建.
     */
    private void ensureBucketExists(String bucket) {
        try {
            boolean found = minioClient.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!found) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
                log.info("Created MinIO bucket for Skills: {}", bucket);
            }
        } catch (Exception e) {
            log.error("MinIO bucket check failed for {}: {}", bucket, e.getMessage());
            throw new RuntimeException("Skill storage initialization failed", e);
        }
    }
}
