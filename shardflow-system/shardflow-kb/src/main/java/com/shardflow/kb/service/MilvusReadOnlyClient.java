package com.shardflow.kb.service;

import io.milvus.client.MilvusServiceClient;
import io.milvus.param.ConnectParam;
import io.milvus.param.R;
import io.milvus.param.RpcStatus;
import io.milvus.param.collection.HasCollectionParam;
import io.milvus.param.collection.ShowCollectionsParam;
import io.milvus.grpc.ShowCollectionsResponse;
import io.milvus.param.collection.CreateDatabaseParam;
import io.milvus.grpc.ListDatabasesResponse;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.List;

@Slf4j
@Service
public class MilvusReadOnlyClient {

    @Value("${shardflow.milvus.host:localhost}")
    private String host;

    @Value("${shardflow.milvus.port:19530}")
    private int port;

    @Value("${shardflow.milvus.database:shardflow_kb}")
    private String database;

    private volatile MilvusServiceClient client;
    private volatile boolean initialized = false;

    /**
     * 懒加载：首次调用时才连接 Milvus，避免启动时 Milvus 不可用导致应用无法启动.
     */
    public synchronized MilvusServiceClient getClient() {
        if (client == null) {
            try {
                connect();
            } catch (Exception e) {
                log.error("Failed to connect to Milvus at {}:{}/{}: {}", host, port, database, e.getMessage());
                throw new RuntimeException("Milvus connection not available", e);
            }
        }
        return client;
    }

    private void connect() {
        // First connect to default database to ensure target database exists
        MilvusServiceClient initClient = new MilvusServiceClient(
            ConnectParam.newBuilder()
                .withHost(host)
                .withPort(port)
                .withDatabaseName("default")
                .build()
        );

        try {
            ensureDatabaseExists(initClient);
        } finally {
            initClient.close();
        }

        // Now connect to the target database
        client = new MilvusServiceClient(
            ConnectParam.newBuilder()
                .withHost(host)
                .withPort(port)
                .withDatabaseName(database)
                .build()
        );
        initialized = true;
        log.info("Milvus read-only client connected to {}:{}/{}", host, port, database);
    }

    private void ensureDatabaseExists(MilvusServiceClient initClient) {
        R<ListDatabasesResponse> resp = initClient.listDatabases();
        if (resp.getStatus() != 0) {
            throw new RuntimeException("Failed to list Milvus databases: " + resp.getMessage());
        }

        List<String> databases = resp.getData().getDbNamesList();
        if (databases.contains(database)) {
            log.info("Milvus database '{}' already exists", database);
            return;
        }

        R<RpcStatus> createResp = initClient.createDatabase(
            CreateDatabaseParam.newBuilder().withDatabaseName(database).build());
        if (createResp.getStatus() != R.Status.Success.getCode()) {
            throw new RuntimeException("Failed to create Milvus database '" + database + "': " + createResp.getMessage());
        }
        log.info("Created Milvus database '{}'", database);
    }

    @PreDestroy
    public void disconnect() {
        if (client != null) {
            client.close();
            log.info("Milvus client disconnected");
        }
    }

    public boolean isHealthy() {
        try {
            R<ShowCollectionsResponse> resp = getClient().showCollections(ShowCollectionsParam.newBuilder().build());
            return resp.getStatus() == 0;
        } catch (Exception e) {
            log.warn("Milvus health check failed: {}", e.getMessage());
            return false;
        }
    }

    public boolean collectionExists(String collectionName) {
        try {
            R<Boolean> resp = getClient().hasCollection(
                HasCollectionParam.newBuilder().withCollectionName(collectionName).build());
            return resp.getStatus() == 0 && Boolean.TRUE.equals(resp.getData());
        } catch (Exception e) {
            log.warn("Milvus collectionExists failed for {}: {}", collectionName, e.getMessage());
            return false;
        }
    }

    public boolean isInitialized() {
        return initialized;
    }
}
