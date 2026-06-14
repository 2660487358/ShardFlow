package com.shardflow.kb.service;

import io.minio.*;
import io.minio.errors.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;

@Slf4j
@Service
@RequiredArgsConstructor
public class MinioStorageService {

    private final MinioClient minioClient;
    private final com.shardflow.kb.config.MinioConfig minioConfig;

    public String upload(String userId, String collectionId, String docCode, MultipartFile file) {
        String bucket = minioConfig.getBucket();
        ensureBucketExists(bucket);

        String ext = extractExtension(file.getOriginalFilename());
        String objectPath = String.format("kb/%s/%s/%s.%s", userId, collectionId, docCode, ext);

        try {
            minioClient.putObject(
                PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(objectPath)
                    .stream(file.getInputStream(), file.getSize(), -1)
                    .contentType(file.getContentType())
                    .build()
            );
            log.info("Uploaded to MinIO: {}/{}", bucket, objectPath);
            return objectPath;
        } catch (Exception e) {
            log.error("MinIO upload failed for {}: {}", objectPath, e.getMessage());
            throw new RuntimeException("File upload to storage failed", e);
        }
    }

    public void delete(String objectPath) {
        try {
            minioClient.removeObject(
                RemoveObjectArgs.builder()
                    .bucket(minioConfig.getBucket())
                    .object(objectPath)
                    .build()
            );
            log.info("Deleted from MinIO: {}/{}", minioConfig.getBucket(), objectPath);
        } catch (Exception e) {
            log.error("MinIO delete failed for {}: {}", objectPath, e.getMessage());
        }
    }

    private void ensureBucketExists(String bucket) {
        try {
            boolean found = minioClient.bucketExists(BucketExistsArgs.builder().bucket(bucket).build());
            if (!found) {
                minioClient.makeBucket(MakeBucketArgs.builder().bucket(bucket).build());
                log.info("Created MinIO bucket: {}", bucket);
            }
        } catch (Exception e) {
            log.error("MinIO bucket check failed: {}", e.getMessage());
            throw new RuntimeException("Storage initialization failed", e);
        }
    }

    private String extractExtension(String filename) {
        if (filename == null || !filename.contains(".")) return "bin";
        return filename.substring(filename.lastIndexOf('.') + 1).toLowerCase();
    }
}
