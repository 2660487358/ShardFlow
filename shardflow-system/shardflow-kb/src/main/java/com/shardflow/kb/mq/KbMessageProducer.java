package com.shardflow.kb.mq;

import com.shardflow.kb.config.RabbitMqConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Slf4j
@Service
@RequiredArgsConstructor
public class KbMessageProducer {

    private final RabbitTemplate rabbitTemplate;

    public void sendUploadCallback(UploadCallbackMessage msg) {
        rabbitTemplate.convertAndSend(
            RabbitMqConfig.EXCHANGE,
            RabbitMqConfig.RK_UPLOAD_COMPLETE,
            msg
        );
        log.info("MQ sent UPLOAD_COMPLETE: task={}, status={}", msg.getTaskId(), msg.getStatus());
    }

    public void sendDeleteCommand(DeleteCommandMessage msg) {
        rabbitTemplate.convertAndSend(
            RabbitMqConfig.EXCHANGE,
            RabbitMqConfig.RK_DELETE_COMMAND,
            msg
        );
        log.info("MQ sent DELETE_COMMAND: kb={}, type={}", msg.getKbId(), msg.getType());
    }

    public void sendDeleteCallback(DeleteCallbackMessage msg) {
        rabbitTemplate.convertAndSend(
            RabbitMqConfig.EXCHANGE,
            RabbitMqConfig.RK_DELETE_COMPLETE,
            msg
        );
        log.info("MQ sent DELETE_COMPLETE: kb={}, status={}", msg.getKbId(), msg.getStatus());
    }
}
