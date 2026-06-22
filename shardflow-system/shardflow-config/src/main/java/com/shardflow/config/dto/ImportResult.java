package com.shardflow.config.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.ArrayList;
import java.util.List;

/**
 * Skill 导入结果响应 DTO.
 *
 * <p>Per Skills管理需求规格文档 IR-10 / ImportResult / FR-3.
 * <p>返回 { created, skipped, failed, details } 统计与明细。
 */
@Data
@NoArgsConstructor
public class ImportResult {

    /** 成功创建数量 */
    private int created;

    /** 跳过数量（如同名跳过） */
    private int skipped;

    /** 失败数量 */
    private int failed;

    /** 导入明细 */
    private List<ImportDetail> details = new ArrayList<>();

    @Data
    @NoArgsConstructor
    public static class ImportDetail {

        private String name;

        /** 状态：created | skipped | failed */
        private String status;

        @JsonProperty("skill_code")
        private String skillCode;

        /** 跳过/失败原因 */
        private String reason;

        public ImportDetail(String name, String status, String skillCode, String reason) {
            this.name = name;
            this.status = status;
            this.skillCode = skillCode;
            this.reason = reason;
        }
    }

    public void incrementCreated() { this.created++; }

    public void incrementSkipped() { this.skipped++; }

    public void incrementFailed() { this.failed++; }
}
