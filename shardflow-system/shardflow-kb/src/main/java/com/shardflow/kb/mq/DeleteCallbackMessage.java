package com.shardflow.kb.mq;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonInclude(JsonInclude.Include.NON_NULL)
public class DeleteCallbackMessage {

    private String kbId;
    private String userId;
    private String type;           // DELETE_COMPLETE
    private String status;         // SUCCESS / FAILED
    private int deletedCount;
    private List<String> failedDocs;
    private String timestamp;
}
