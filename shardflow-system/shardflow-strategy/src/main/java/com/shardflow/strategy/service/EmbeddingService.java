package com.shardflow.strategy.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class EmbeddingService {
    private static final Logger log = LoggerFactory.getLogger(EmbeddingService.class);
    private final HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();
    private final ObjectMapper objectMapper;
    private final String apiKey;
    private final String apiBaseUrl;

    public EmbeddingService(ObjectMapper objectMapper,
                            @Value("${shardflow.openai.api-key:}") String apiKey,
                            @Value("${shardflow.openai.base-url:https://api.openai.com}") String apiBaseUrl) {
        this.objectMapper = objectMapper;
        this.apiKey = apiKey;
        this.apiBaseUrl = apiBaseUrl;
    }

    public List<Float> generate(String text) {
        if (apiKey == null || apiKey.isBlank()) {
            log.warn("OpenAI API key not configured, skipping embedding generation");
            return null;
        }
        try {
            String body = objectMapper.writeValueAsString(Map.of(
                "input", text,
                "model", "text-embedding-3-small",
                "dimensions", 1536
            ));
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(apiBaseUrl + "/v1/embeddings"))
                .header("Authorization", "Bearer " + apiKey)
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode root = objectMapper.readTree(response.body());
            JsonNode embedding = root.path("data").get(0).path("embedding");
            List<Float> result = new ArrayList<>();
            for (JsonNode val : embedding) {
                result.add(val.floatValue());
            }
            return result;
        } catch (Exception e) {
            log.warn("Failed to generate embedding: {}", e.getMessage());
            return null;
        }
    }

    public String toVectorString(List<Float> embedding) {
        if (embedding == null) return null;
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < embedding.size(); i++) {
            if (i > 0) sb.append(",");
            sb.append(embedding.get(i));
        }
        sb.append("]");
        return sb.toString();
    }

    @Async
    public void generateAndStoreAsync(StrategySaveHandler handler) {
        List<Float> embedding = generate(handler.getText());
        if (embedding != null) {
            handler.onEmbeddingGenerated(toVectorString(embedding));
        }
    }

    public interface StrategySaveHandler {
        String getText();
        void onEmbeddingGenerated(String vectorString);
    }
}
