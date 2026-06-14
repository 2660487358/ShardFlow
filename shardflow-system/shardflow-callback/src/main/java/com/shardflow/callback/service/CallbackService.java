package com.shardflow.callback.service;

import java.util.Map;

public interface CallbackService {

    Map<String, Object> sessionComplete(Map<String, Object> body);

    Map<String, Object> writeAudit(Map<String, Object> body);

    Map<String, Object> reportProgress(Map<String, Object> body);

    Map<String, Object> saveShard(Map<String, Object> body);

    Map<String, Object> saveProfile(Map<String, Object> body);

    Map<String, Object> saveMemory(Map<String, Object> body);

    Map<String, Object> saveStrategyRecord(Map<String, Object> body);
}
