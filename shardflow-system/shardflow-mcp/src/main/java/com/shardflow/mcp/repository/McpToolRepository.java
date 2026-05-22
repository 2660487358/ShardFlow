package com.shardflow.mcp.repository;

import com.shardflow.common.entity.McpToolEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface McpToolRepository extends JpaRepository<McpToolEntity, String> {
    List<McpToolEntity> findByStatus(String status);
}
