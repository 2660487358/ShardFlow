package com.shardflow.mcp.validator;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import com.networknt.schema.Error;
import com.networknt.schema.Schema;
import com.networknt.schema.SchemaLocation;
import com.networknt.schema.SchemaRegistry;
import com.networknt.schema.SpecificationVersion;
import com.networknt.schema.dialect.Dialects;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * JSON Schema 校验器.
 * 校验 input_schema 和 output_schema 的合法性 (FR-REG-002).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class JsonSchemaValidator {

    private final ObjectMapper objectMapper;

    /**
     * 校验 JSON Schema 是否合法.
     *
     * @param schemaMap Schema 定义（Map 形式）
     * @param fieldName 字段名（用于错误提示）
     * @return 校验失败信息列表，空列表表示校验通过
     */
    public List<String> validateSchema(java.util.Map<String, Object> schemaMap, String fieldName) {
        List<String> errors = new ArrayList<>();
        if (schemaMap == null || schemaMap.isEmpty()) {
            return errors;
        }
        try {
            JsonNode schemaNode = objectMapper.valueToTree(schemaMap);
            SchemaRegistry registry = SchemaRegistry.withDialect(Dialects.getDraft7());
            Schema metaSchema = registry.getSchema(SchemaLocation.of(SpecificationVersion.DRAFT_7.getDialectId()));
            List<Error> messages = metaSchema.validate(schemaNode);
            for (Error msg : messages) {
                errors.add(fieldName + ": " + msg.getMessage());
            }
        } catch (Exception e) {
            log.warn("JSON Schema validation failed for {}: {}", fieldName, e.getMessage());
            errors.add(fieldName + ": invalid JSON Schema structure - " + e.getMessage());
        }
        return errors;
    }
}
