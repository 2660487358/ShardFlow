package com.shardflow.common.dto.profile;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * Response DTO for user profile update.
 * Per spec section 7.9: Response 200 OK
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class UserProfileUpdateResponse {

    private String profileId;

    private String status;

    private Integer profileVersion;
}
