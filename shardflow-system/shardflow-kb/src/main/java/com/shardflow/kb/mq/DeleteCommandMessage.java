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
public class DeleteCommandMessage {

    private String kbId;
    private String type;          // DELETE_KB / DELETE_DOC
    private String docId;         // for DELETE_DOC
    private String userId;        // for resolving collection name kb_chunks_{userId}
    private List<String> docIdList;  // for DELETE_KB
    private String initiatedAt;
}
