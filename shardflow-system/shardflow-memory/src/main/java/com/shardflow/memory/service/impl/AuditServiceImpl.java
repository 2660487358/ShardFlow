package com.shardflow.memory.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.shardflow.common.entity.AuditLogEntity;
import com.shardflow.memory.repository.AuditLogRepository;
import com.shardflow.memory.service.AuditService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class AuditServiceImpl implements AuditService {

    private final AuditLogRepository auditLogRepository;

    @Override
    public Map<String, Object> queryAuditLogs(String userId, String operation, String startTime, String endTime, int page, int pageSize) {
        LambdaQueryWrapper<AuditLogEntity> wrapper = new LambdaQueryWrapper<>();

        if (userId != null && !userId.isBlank()) {
            wrapper.eq(AuditLogEntity::getUserId, userId);
        }
        if (operation != null && !operation.isBlank()) {
            wrapper.like(AuditLogEntity::getToolName, operation);
        }
        if (startTime != null && !startTime.isBlank()) {
            Instant start = Instant.parse(startTime);
            wrapper.ge(AuditLogEntity::getCreatedAt, start);
        }
        if (endTime != null && !endTime.isBlank()) {
            Instant end = Instant.parse(endTime);
            wrapper.le(AuditLogEntity::getCreatedAt, end);
        }

        wrapper.orderByDesc(AuditLogEntity::getCreatedAt);

        Page<AuditLogEntity> result = auditLogRepository.selectPage(
                new Page<>(page, pageSize), wrapper);

        Map<String, Object> response = new HashMap<>();
        response.put("logs", result.getRecords());
        response.put("total", result.getTotal());
        response.put("page", page);
        response.put("pageSize", pageSize);
        return response;
    }

    @Override
    @Transactional
    public int cleanupOldLogs(int retentionDays) {
        Instant cutoff = Instant.now().minus(java.time.Duration.ofDays(retentionDays));

        int deleted = auditLogRepository.delete(
                new LambdaQueryWrapper<AuditLogEntity>()
                        .lt(AuditLogEntity::getCreatedAt, cutoff));

        log.info("Cleaned up {} audit logs older than {} days", deleted, retentionDays);
        return deleted;
    }
}
