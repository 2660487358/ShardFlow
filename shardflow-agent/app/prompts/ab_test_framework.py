"""A/B 测试框架 — L2 概念摘要质量评估 (T3.5).

为阶段3 P1 的 L2 概念摘要提供 A/B 测试基础设施：
- 实验分组：control（硬窗口 8 轮）vs experiment（L2 摘要）
- 指标采集：压缩率、关键实体保留率、人工评分
- 评估报告：生成 AC-17/AC-19 验收所需的统计报告

使用方式：
    from app.prompts.ab_test_framework import ab_framework
    ab_framework.assign_group("user_123")  # 分组
    ab_framework.record_metric("user_123", "compression_ratio", 0.25)
    report = ab_framework.generate_report()
"""
import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 实验配置
# ---------------------------------------------------------------------------

class ExperimentConfig:
    """A/B 实验配置."""

    # 实验名称
    EXPERIMENT_NAME = "l2_concept_summary_p1"

    # 分组比例：control 50%, experiment 50%
    CONTROL_GROUP = "control"          # 基线组：硬窗口 8 轮
    EXPERIMENT_GROUP = "experiment"    # 实验组：L2 摘要

    # 评估指标阈值（AC-17）
    TARGET_COMPRESSION_RATIO_MIN = 0.20  # 压缩率下限 20%
    TARGET_COMPRESSION_RATIO_MAX = 0.30  # 压缩率上限 30%
    TARGET_ENTITY_RETENTION = 0.95       # 关键实体保留率 ≥ 95%

    # 人工评分阈值（AC-19）
    TARGET_MANUAL_SCORE_LIFT = 0.05      # 实验组评分不低于基线 5%

    # 样本量要求
    MIN_SAMPLE_SIZE = 30                 # 每组最少样本量


# ---------------------------------------------------------------------------
# A/B 测试框架
# ---------------------------------------------------------------------------

class ABTestFramework:
    """A/B 测试框架 — 管理分组、指标采集与报告生成."""

    def __init__(self) -> None:
        # user_id -> group
        self._assignments: dict[str, str] = {}
        # group -> metric_name -> list of values
        self._metrics: dict[str, dict[str, list[float]]] = {
            ExperimentConfig.CONTROL_GROUP: {},
            ExperimentConfig.EXPERIMENT_GROUP: {},
        }
        # 人工评分：group -> list of {session_id, score, evaluator}
        self._manual_scores: dict[str, list[dict[str, Any]]] = {
            ExperimentConfig.CONTROL_GROUP: [],
            ExperimentConfig.EXPERIMENT_GROUP: [],
        }

    def assign_group(self, user_id: str, force_group: str | None = None) -> str:
        """为用户分配实验分组（确定性哈希分配，同一用户始终在同一组）.

        Args:
            user_id: 用户 ID
            force_group: 强制指定分组（用于测试）

        Returns:
            "control" 或 "experiment"
        """
        if force_group and force_group in (ExperimentConfig.CONTROL_GROUP, ExperimentConfig.EXPERIMENT_GROUP):
            self._assignments[user_id] = force_group
            return force_group

        if user_id in self._assignments:
            return self._assignments[user_id]

        # 确定性分配：基于 user_id 哈希，保证同一用户始终在同一组
        hash_val = sum(ord(c) for c in user_id)
        group = (
            ExperimentConfig.EXPERIMENT_GROUP
            if hash_val % 2 == 0
            else ExperimentConfig.CONTROL_GROUP
        )
        self._assignments[user_id] = group
        logger.info("Assigned user %s to group %s", user_id, group)
        return group

    def get_group(self, user_id: str) -> str | None:
        """获取用户已分配的分组."""
        return self._assignments.get(user_id)

    def record_metric(self, user_id: str, metric_name: str, value: float) -> None:
        """记录评估指标.

        Args:
            user_id: 用户 ID（用于确定分组）
            metric_name: 指标名（compression_ratio / entity_retention / token_cost）
            value: 指标值
        """
        group = self.assign_group(user_id)
        if metric_name not in self._metrics[group]:
            self._metrics[group][metric_name] = []
        self._metrics[group][metric_name].append(value)
        logger.debug(
            "Recorded metric %s=%.3f for user=%s group=%s",
            metric_name, value, user_id, group,
        )

    def record_manual_score(
        self, user_id: str, session_id: str, score: float, evaluator: str = "",
    ) -> None:
        """记录人工评分（1-5 分制）.

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            score: 评分（1.0-5.0）
            evaluator: 评估者标识
        """
        group = self.assign_group(user_id)
        self._manual_scores[group].append({
            "session_id": session_id,
            "score": score,
            "evaluator": evaluator,
            "timestamp": time.time(),
        })

    def _mean(self, values: list[float]) -> float:
        """计算平均值."""
        if not values:
            return 0.0
        return sum(values) / len(values)

    def generate_report(self) -> dict[str, Any]:
        """生成 A/B 测试评估报告.

        覆盖 AC-17（压缩率 20%-30%，关键实体保留率 ≥ 95%）
        和 AC-19（人工评分不低于基线 5%）。

        Returns:
            包含统计指标和验收结论的字典
        """
        control = self._metrics[ExperimentConfig.CONTROL_GROUP]
        experiment = self._metrics[ExperimentConfig.EXPERIMENT_GROUP]

        # 压缩率统计（仅实验组有此指标）
        exp_compression = experiment.get("compression_ratio", [])
        compression_ratio_mean = self._mean(exp_compression)

        # 关键实体保留率统计（仅实验组有此指标）
        exp_retention = experiment.get("entity_retention", [])
        entity_retention_mean = self._mean(exp_retention)

        # Token 成本对比
        ctrl_token = control.get("token_cost", [])
        exp_token = experiment.get("token_cost", [])
        ctrl_token_mean = self._mean(ctrl_token)
        exp_token_mean = self._mean(exp_token)
        token_cost_reduction = (
            (ctrl_token_mean - exp_token_mean) / ctrl_token_mean
            if ctrl_token_mean > 0 else 0.0
        )

        # 人工评分对比
        ctrl_scores = [s["score"] for s in self._manual_scores[ExperimentConfig.CONTROL_GROUP]]
        exp_scores = [s["score"] for s in self._manual_scores[ExperimentConfig.EXPERIMENT_GROUP]]
        ctrl_score_mean = self._mean(ctrl_scores)
        exp_score_mean = self._mean(exp_scores)
        score_lift = (
            (exp_score_mean - ctrl_score_mean) / ctrl_score_mean
            if ctrl_score_mean > 0 else 0.0
        )

        # 验收判定
        ac17_pass = (
            ExperimentConfig.TARGET_COMPRESSION_RATIO_MIN <= compression_ratio_mean
            <= ExperimentConfig.TARGET_COMPRESSION_RATIO_MAX
            and entity_retention_mean >= ExperimentConfig.TARGET_ENTITY_RETENTION
        )
        ac19_pass = score_lift >= ExperimentConfig.TARGET_MANUAL_SCORE_LIFT

        report = {
            "experiment_name": ExperimentConfig.EXPERIMENT_NAME,
            "generated_at": time.time(),
            "sample_sizes": {
                "control": len(ctrl_scores),
                "experiment": len(exp_scores),
                "min_required": ExperimentConfig.MIN_SAMPLE_SIZE,
            },
            "metrics": {
                "compression_ratio": {
                    "mean": compression_ratio_mean,
                    "target_range": [
                        ExperimentConfig.TARGET_COMPRESSION_RATIO_MIN,
                        ExperimentConfig.TARGET_COMPRESSION_RATIO_MAX,
                    ],
                    "samples": len(exp_compression),
                },
                "entity_retention": {
                    "mean": entity_retention_mean,
                    "target": ExperimentConfig.TARGET_ENTITY_RETENTION,
                    "samples": len(exp_retention),
                },
                "token_cost": {
                    "control_mean": ctrl_token_mean,
                    "experiment_mean": exp_token_mean,
                    "reduction": token_cost_reduction,
                },
                "manual_score": {
                    "control_mean": ctrl_score_mean,
                    "experiment_mean": exp_score_mean,
                    "lift": score_lift,
                    "target_lift": ExperimentConfig.TARGET_MANUAL_SCORE_LIFT,
                },
            },
            "acceptance": {
                "AC-17": {
                    "description": "压缩率 20%-30%，关键实体保留率 ≥ 95%",
                    "passed": ac17_pass,
                    "compression_ratio_in_range": (
                        ExperimentConfig.TARGET_COMPRESSION_RATIO_MIN
                        <= compression_ratio_mean
                        <= ExperimentConfig.TARGET_COMPRESSION_RATIO_MAX
                    ),
                    "entity_retention_meets_threshold": (
                        entity_retention_mean >= ExperimentConfig.TARGET_ENTITY_RETENTION
                    ),
                },
                "AC-19": {
                    "description": "A/B 测试验证摘要质量，不低于基线 5%",
                    "passed": ac19_pass,
                    "score_lift": score_lift,
                    "target_lift": ExperimentConfig.TARGET_MANUAL_SCORE_LIFT,
                },
            },
            "overall_passed": ac17_pass and ac19_pass,
        }

        logger.info(
            "A/B test report generated: AC-17=%s, AC-19=%s, overall=%s",
            ac17_pass, ac19_pass, report["overall_passed"],
        )
        return report

    def export_report_json(self, filepath: str) -> None:
        """导出评估报告为 JSON 文件."""
        report = self.generate_report()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("A/B test report exported to %s", filepath)

    def reset(self) -> None:
        """重置所有分组和指标（用于测试）."""
        self._assignments.clear()
        self._metrics = {
            ExperimentConfig.CONTROL_GROUP: {},
            ExperimentConfig.EXPERIMENT_GROUP: {},
        }
        self._manual_scores = {
            ExperimentConfig.CONTROL_GROUP: [],
            ExperimentConfig.EXPERIMENT_GROUP: [],
        }


# 全局单例
ab_framework = ABTestFramework()
