package com.shardflow.strategy.controller;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.shardflow.common.dto.Result;
import com.shardflow.common.dto.StrategySearchRequest;
import com.shardflow.common.entity.StrategyEntity;
import com.shardflow.common.entity.StrategyFeedbackEntity;
import com.shardflow.strategy.repository.StrategyFeedbackRepository;
import com.shardflow.strategy.repository.StrategyRepository;
import com.shardflow.strategy.service.StrategyService;
import com.shardflow.usercontext.context.UserContext;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/strategies")
@RequiredArgsConstructor
public class StrategyController {

    private final StrategyService strategyService;
    private final StrategyFeedbackRepository feedbackRepository;
    private final StrategyRepository strategyRepository;

    @PostMapping("/search")
    public Result<Map<String, Object>> search(@RequestBody StrategySearchRequest request) {
        return Result.ok(strategyService.semanticSearch(request));
    }

    @PostMapping("/{id}/feedback")
    public Result<Map<String, Object>> feedback(@PathVariable String id, @RequestBody Map<String, String> body) {
        String feedbackType = body.getOrDefault("feedback", "neutral");
        String comment = body.get("comment");

        StrategyFeedbackEntity fb = new StrategyFeedbackEntity();
        fb.setStrategyCode(id);
        fb.setUserId(UserContext.getUserId());
        fb.setFeedbackType(feedbackType);
        fb.setComment(comment);
        feedbackRepository.insert(fb);

        // Update success score based on feedback
        StrategyEntity strategy = strategyRepository.selectOne(
            new LambdaQueryWrapper<StrategyEntity>().eq(StrategyEntity::getStrategyCode, id));
        if (strategy != null) {
            double delta = "like".equals(feedbackType) ? 0.05 : "dislike".equals(feedbackType) ? -0.05 : 0;
            double newScore = Math.max(0, Math.min(1, strategy.getSuccessScore() + delta));
            strategy.setSuccessScore(newScore);
            strategyRepository.updateById(strategy);
        }

        return Result.ok(Map.of("success", true, "feedback_id", fb.getId()));
    }
}
