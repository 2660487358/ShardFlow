package com.shardflow.kb.config;

import org.springframework.amqp.core.*;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMqConfig {

    public static final String EXCHANGE = "kb.events";

    // Queues
    public static final String QUEUE_UPLOAD_CALLBACK = "kb.upload.callback";
    public static final String QUEUE_UPLOAD_PROGRESS = "kb.upload.progress";
    public static final String QUEUE_DELETE_COMMAND = "kb.delete.command";
    public static final String QUEUE_DELETE_CALLBACK = "kb.delete.callback";

    // Dead Letter
    public static final String DLX = "kb.dlx";
    public static final String DLQ = "kb.dlq";

    // Routing keys
    public static final String RK_UPLOAD_COMPLETE = "upload.complete";
    public static final String RK_UPLOAD_PROGRESS = "upload.progress";
    public static final String RK_DELETE_COMMAND = "delete.command";
    public static final String RK_DELETE_COMPLETE = "delete.complete";

    @Bean
    public TopicExchange kbExchange() {
        return new TopicExchange(EXCHANGE, true, false);
    }

    @Bean
    public Queue uploadCallbackQueue() {
        return QueueBuilder.durable(QUEUE_UPLOAD_CALLBACK)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DLQ)
                .build();
    }

    @Bean
    public Queue uploadProgressQueue() {
        return QueueBuilder.durable(QUEUE_UPLOAD_PROGRESS)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DLQ)
                .build();
    }

    @Bean
    public Queue deleteCommandQueue() {
        return QueueBuilder.durable(QUEUE_DELETE_COMMAND)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DLQ)
                .build();
    }

    @Bean
    public Queue deleteCallbackQueue() {
        return QueueBuilder.durable(QUEUE_DELETE_CALLBACK)
                .deadLetterExchange(DLX)
                .deadLetterRoutingKey(DLQ)
                .build();
    }

    @Bean
    public TopicExchange deadLetterExchange() {
        return new TopicExchange(DLX, true, false);
    }

    @Bean
    public Queue deadLetterQueue() {
        return QueueBuilder.durable(DLQ).build();
    }

    @Bean
    public Binding dlqBinding() {
        return BindingBuilder.bind(deadLetterQueue()).to(deadLetterExchange()).with(DLQ);
    }

    @Bean
    public Binding uploadCallbackBinding() {
        return BindingBuilder.bind(uploadCallbackQueue()).to(kbExchange()).with(RK_UPLOAD_COMPLETE);
    }

    @Bean
    public Binding uploadProgressBinding() {
        return BindingBuilder.bind(uploadProgressQueue()).to(kbExchange()).with(RK_UPLOAD_PROGRESS);
    }

    @Bean
    public Binding deleteCommandBinding() {
        return BindingBuilder.bind(deleteCommandQueue()).to(kbExchange()).with(RK_DELETE_COMMAND);
    }

    @Bean
    public Binding deleteCallbackBinding() {
        return BindingBuilder.bind(deleteCallbackQueue()).to(kbExchange()).with(RK_DELETE_COMPLETE);
    }

    @Bean
    public MessageConverter messageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
