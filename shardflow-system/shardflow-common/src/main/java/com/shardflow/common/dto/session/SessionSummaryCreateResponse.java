package com.shardflow.common.dto.session;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;

/**
 * Response DTO for session state summary creation.
 * Per spec section 7.6: Response 201 Created
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class SessionSummaryCreateResponse {

    private String summaryId;

    private String status;

    private Instant createdAt;
}
