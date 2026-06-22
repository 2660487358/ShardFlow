package com.shardflow.config.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

/**
 * Skills 管理 MinIO 存储配置.
 *
 * <p>Per Skills管理需求规格文档 DR-6 / 实施计划 P1.3.3.
 * <p>绑定 shardflow.minio.skill-bucket 属性，Artifact 存储路径规范：
 * {@code minio://{skill_bucket}/{user_id}/{skill_code}/{version_tag}/{file_name}}.
 *
 * <p>注意：本配置类不创建 MinioClient Bean。MinioClient 由 shardflow-kb 模块的
 * MinioConfig 统一创建，shardflow-app 同时引入 kb 与 config，运行时复用同一 Bean，
 * 避免重复 Bean 定义冲突。
 */
@Getter
@Setter
@Configuration
@ConfigurationProperties(prefix = "shardflow.minio")
public class SkillMinioConfig {

    /** Skill Artifact 存储 Bucket 名称，默认 shardflow-skills */
    private String skillBucket = "shardflow-skills";
}
