package com.shardflow.kb.service;

import com.shardflow.kb.mq.UploadCallbackMessage;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class KbProgressService {

    private final SimpMessagingTemplate messagingTemplate;

    public void pushProgress(String userId, String documentId, String status, int progress, String error) {
        Map<String, Object> payload = Map.of(
            "documentId", documentId,
            "status", status,
            "progress", progress,
            "error", error != null ? error : ""
        );
        messagingTemplate.convertAndSend("/topic/kb/progress/" + userId, (Object) payload);
        log.debug("WS progress: user={}, doc={}, status={}, pct={}", userId, documentId, status, progress);
    }

    public void pushFromUploadCallback(UploadCallbackMessage msg, String documentId, String userId) {
        String status = "SUCCESS".equals(msg.getStatus()) ? "READY" : "ERROR";
        int progress = "SUCCESS".equals(msg.getStatus()) ? 100 : 0;
        String error = msg.getError() != null ? msg.getError().getMessage() : null;
        pushProgress(userId, documentId, status, progress, error);
    }
}
