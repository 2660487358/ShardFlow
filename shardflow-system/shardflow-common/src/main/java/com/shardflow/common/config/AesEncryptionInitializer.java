package com.shardflow.common.config;

import com.shardflow.common.util.AesEncryptionUtil;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Initializes {@link AesEncryptionUtil} master key from Spring configuration at startup.
 */
@Slf4j
@Component
public class AesEncryptionInitializer {

    @Value("${shardflow.model-key-master:}")
    private String masterKeyBase64;

    @PostConstruct
    public void init() {
        if (masterKeyBase64 == null || masterKeyBase64.isBlank()) {
            log.warn("shardflow.model-key-master is not configured — AES encryption/decryption will fail until it is set");
            return;
        }
        try {
            AesEncryptionUtil.initMasterKey(masterKeyBase64);
            log.info("AES master key initialized successfully");
        } catch (Exception e) {
            log.error("Failed to initialize AES master key: {}", e.getMessage());
        }
    }
}
