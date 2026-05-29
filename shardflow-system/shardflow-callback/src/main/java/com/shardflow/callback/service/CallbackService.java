package com.shardflow.callback.service;

import com.shardflow.common.dto.ShardSaveRequest;
import java.util.Map;

public interface CallbackService {

    Map<String, Object> saveShard(ShardSaveRequest request);

    Map<String, Object> saveStrategy(Map<String, Object> body);

    Map<String, Object> sessionComplete(Map<String, Object> body);

    Map<String, Object> writeAudit(Map<String, Object> body);

    Map<String, Object> reportProgress(Map<String, Object> body);
}
