package com.shardflow.strategy.milvus;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;

@Slf4j
@Service
public class MilvusClientService {

    private volatile HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String milvusHost;
    private final int milvusPort;
    private final String dbName;

    public MilvusClientService(ObjectMapper objectMapper,
                               @Value("${shardflow.milvus.host:localhost}") String milvusHost,
                               @Value("${shardflow.milvus.port:19530}") int milvusPort,
                               @Value("${shardflow.milvus.db:shardflow_kb}") String dbName) {
        this.objectMapper = objectMapper;
        this.milvusHost = milvusHost;
        this.milvusPort = milvusPort;
        this.dbName = dbName;
    }

    private HttpClient getHttpClient() {
        if (httpClient == null) {
            synchronized (this) {
                if (httpClient == null) {
                    httpClient = HttpClient.newBuilder()
                        .connectTimeout(Duration.ofSeconds(10))
                        .build();
                }
            }
        }
        return httpClient;
    }

    public List<Map<String, Object>> search(String collectionName, List<Float> vector,
                                             int topK, String outputField) {
        try {
            ObjectNode body = objectMapper.createObjectNode();
            body.put("collectionName", collectionName);
            body.put("dbName", dbName);
            ArrayNode vecNode = body.putArray("vector");
            for (Float v : vector) vecNode.add(v);
            body.put("limit", topK);
            ArrayNode outputFields = body.putArray("outputFields");
            outputFields.add(outputField);

            String url = "http://" + milvusHost + ":" + milvusPort + "/v2/vectordb/entities/search";
            HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .timeout(Duration.ofSeconds(10))
                .POST(HttpRequest.BodyPublishers.ofString(objectMapper.writeValueAsString(body)))
                .build();
            HttpResponse<String> response = getHttpClient().send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                JsonNode root = objectMapper.readTree(response.body());
                JsonNode data = root.path("data");
                List<Map<String, Object>> results = new ArrayList<>();
                for (JsonNode item : data) {
                    Map<String, Object> result = new HashMap<>();
                    result.put("id", item.path("id").asText());
                    result.put("distance", item.path("distance").asDouble());
                    result.put("strategy_id", item.path(outputField).asText());
                    results.add(result);
                }
                return results;
            }
            log.warn("Milvus search returned status {}: {}", response.statusCode(), response.body());
            return Collections.emptyList();
        } catch (Exception e) {
            log.warn("Milvus search failed: {}", e.getMessage());
            return Collections.emptyList();
        }
    }
}
