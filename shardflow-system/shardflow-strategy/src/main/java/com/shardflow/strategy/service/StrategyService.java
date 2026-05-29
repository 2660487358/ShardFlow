package com.shardflow.strategy.service;

import com.shardflow.common.dto.StrategySearchRequest;
import java.util.Map;

public interface StrategyService {

    Map<String, Object> semanticSearch(StrategySearchRequest request);
}
