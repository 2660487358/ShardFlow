package com.shardflow.kb.service;

import com.shardflow.kb.grpc.Knowledge;
import com.shardflow.kb.grpc.KnowledgeServiceGrpc;
import com.shardflow.kb.config.GrpcConfig;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class GrpcKnowledgeClient {

    private final GrpcConfig grpcConfig;
    private final GrpcCircuitBreaker circuitBreaker;
    private ManagedChannel channel;
    private KnowledgeServiceGrpc.KnowledgeServiceBlockingStub stub;

    public GrpcKnowledgeClient(GrpcConfig grpcConfig, GrpcCircuitBreaker circuitBreaker) {
        this.grpcConfig = grpcConfig;
        this.circuitBreaker = circuitBreaker;
    }

    @PostConstruct
    public void init() {
        channel = ManagedChannelBuilder
                .forAddress(grpcConfig.getPythonHost(), grpcConfig.getPythonPort())
                .usePlaintext()
                .build();
        stub = KnowledgeServiceGrpc.newBlockingStub(channel);
        log.info("gRPC channel created to {}:{}", grpcConfig.getPythonHost(), grpcConfig.getPythonPort());
    }

    @PreDestroy
    public void shutdown() throws InterruptedException {
        if (channel != null) {
            channel.shutdown().awaitTermination(5, TimeUnit.SECONDS);
            log.info("gRPC channel shut down");
        }
    }

    public Knowledge.TaskAck submitUploadTask(String taskId, String kbId, String minioUrl,
                                               String filename, String fileType, long fileSize,
                                               String uploader, String uploadTime) {
        Knowledge.FileMetadata metadata = Knowledge.FileMetadata.newBuilder()
                .setFilename(filename)
                .setFileType(fileType)
                .setFileSize(fileSize)
                .setUploader(uploader)
                .setUploadTime(uploadTime)
                .build();

        Knowledge.UploadTask task = Knowledge.UploadTask.newBuilder()
                .setTaskId(taskId)
                .setKbId(kbId)
                .setMinioUrl(minioUrl)
                .setMetadata(metadata)
                .setPriority(0)
                .build();

        return circuitBreaker.execute(
            () -> {
                try {
                    Knowledge.TaskAck ack = stub
                            .withDeadlineAfter(grpcConfig.getTimeoutSeconds(), TimeUnit.SECONDS)
                            .submitUploadTask(task);
                    log.info("gRPC SubmitUploadTask: task={}, accepted={}, msg={}",
                            taskId, ack.getAccepted(), ack.getMessage());
                    return ack;
                } catch (StatusRuntimeException e) {
                    log.error("gRPC SubmitUploadTask failed: task={}, status={}", taskId, e.getStatus());
                    throw new RuntimeException("gRPC call failed: " + e.getStatus().getDescription(), e);
                }
            },
            () -> {
                log.warn("gRPC circuit breaker open for task={}, returning fallback", taskId);
                return Knowledge.TaskAck.newBuilder()
                        .setTaskId(taskId)
                        .setAccepted(false)
                        .setMessage("Service busy, please retry later")
                        .build();
            }
        );
    }
}
