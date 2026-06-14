package com.shardflow.kb.mq;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UploadCallbackMessage {

    private String taskId;
    private String type;          // UPLOAD_COMPLETE
    private String status;        // SUCCESS / FAILED
    private String kbId;
    private UploadResult result;
    private UploadError error;
    private String timestamp;

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class UploadResult {
        private String docId;
        private int chunkCount;
        private String embeddingModel;
        private long processTimeMs;
        private long tokenCount;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class UploadError {
        private String code;
        private String message;
        private boolean retryable;
    }
}
