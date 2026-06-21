"""L2 概念摘要质量评估脚本 (T3.5).

评估指标（AC-17/AC-19）：
- 压缩率：压缩后摘要长度 / 原始对话长度，目标 20%-30%
- 关键实体保留率：摘要中保留的关键实体 / 原始对话中的关键实体，目标 ≥ 95%
- 人工评分：实验组评分 vs 基线组评分，目标不低于基线 5%

使用方式：
    cd shardflow-agent
    python -m app.prompts.evaluate_compress_quality --samples 50

或作为模块导入：
    from app.prompts.evaluate_compress_quality import CompressionQualityEvaluator
    evaluator = CompressionQualityEvaluator()
    result = evaluator.evaluate_sample(messages, summary, entities)
"""
import argparse
import json
import logging
import re
from typing import Any

from app.prompts.ab_test_framework import (
    ExperimentConfig,
    ab_framework,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 关键实体提取（简化版 NER）
# ---------------------------------------------------------------------------

# 简化的实体识别正则模式（生产环境应使用专业 NER 模型）
ENTITY_PATTERNS = {
    "person": re.compile(r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)*)|([\u4e00-\u9fa5]{2,4}(?:老师|先生|女士|经理))"),
    "date": re.compile(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?|\d{1,2}月\d{1,2}日|今天|昨天|明天|下周"),
    "number": re.compile(r"\d+(?:\.\d+)?(?:%|万|亿|个|条|次|轮|步)?"),
    "tech_term": re.compile(
        r"[A-Z][a-zA-Z]+(?:[A-Z][a-zA-Z]+)*"  # CamelCase
        r"|[a-z]+_[a-z_]+"  # snake_case
        r"|\b(?:API|HTTP|gRPC|REST|JSON|XML|SQL|Redis|Milvus|PostgreSQL|Python|Java|React)\b"
    ),
    "business_id": re.compile(r"[a-z]+_\w{6,}|sess_\w+|task_\w+|user_\w+"),
}


def extract_entities(text: str) -> set[str]:
    """从文本中提取关键实体（简化版）.

    生产环境应替换为专业 NER 服务（如 spaCy / LAC / 自训模型）。
    """
    if not text:
        return set()
    entities: set[str] = set()
    for pattern in ENTITY_PATTERNS.values():
        for match in pattern.finditer(text):
            entity = match.group().strip()
            if entity and len(entity) >= 2:
                entities.add(entity)
    return entities


# ---------------------------------------------------------------------------
# 压缩质量评估器
# ---------------------------------------------------------------------------

class CompressionQualityEvaluator:
    """评估 L2 概念摘要的压缩质量."""

    def __init__(self) -> None:
        self.ab = ab_framework

    def evaluate_sample(
        self,
        original_messages: list[dict[str, str]],
        compressed_summary: str,
        structured_summary: dict[str, Any] | None = None,
        user_id: str = "eval_user",
        force_group: str | None = None,
    ) -> dict[str, Any]:
        """评估单个样本的压缩质量.

        Args:
            original_messages: 原始对话消息列表 [{"role": "user", "content": "..."}]
            compressed_summary: 压缩后的自然语言摘要
            structured_summary: 结构化摘要（含 entities 字段）
            user_id: 用户 ID（用于 A/B 分组）
            force_group: 强制指定分组

        Returns:
            评估结果字典，包含 compression_ratio / entity_retention / entities
        """
        # 计算原始对话长度（字符数）
        original_text = "\n".join(m.get("content", "") for m in original_messages)
        original_length = len(original_text)
        compressed_length = len(compressed_summary)

        # 压缩率 = 压缩后长度 / 原始长度
        compression_ratio = (
            compressed_length / original_length if original_length > 0 else 0.0
        )

        # 关键实体保留率
        original_entities = extract_entities(original_text)
        # 优先使用结构化摘要中的 entities 字段
        if structured_summary and structured_summary.get("entities"):
            compressed_entities = set(structured_summary["entities"])
        else:
            compressed_entities = extract_entities(compressed_summary)

        if original_entities:
            retained = original_entities & compressed_entities
            entity_retention = len(retained) / len(original_entities)
        else:
            entity_retention = 1.0  # 无实体可保留时视为 100%

        # 记录到 A/B 框架
        group = self.ab.assign_group(user_id, force_group=force_group)
        if group == ExperimentConfig.EXPERIMENT_GROUP:
            self.ab.record_metric(user_id, "compression_ratio", compression_ratio)
            self.ab.record_metric(user_id, "entity_retention", entity_retention)
            # Token 成本估算（4 字符 ≈ 1 token）
            self.ab.record_metric(
                user_id, "token_cost",
                compressed_length / 4,
            )
        else:
            # 基线组：硬窗口，Token 成本为原始长度
            self.ab.record_metric(
                user_id, "token_cost",
                original_length / 4,
            )

        result = {
            "compression_ratio": compression_ratio,
            "entity_retention": entity_retention,
            "original_length": original_length,
            "compressed_length": compressed_length,
            "original_entities": sorted(original_entities),
            "compressed_entities": sorted(compressed_entities),
            "retained_entities": sorted(original_entities & compressed_entities),
            "group": group,
        }
        logger.debug(
            "Evaluated sample: ratio=%.3f, retention=%.3f, group=%s",
            compression_ratio, entity_retention, group,
        )
        return result

    def evaluate_batch(
        self,
        samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """批量评估样本并生成报告.

        Args:
            samples: 样本列表，每个样本包含 original_messages / compressed_summary /
                    structured_summary / user_id

        Returns:
            A/B 测试评估报告
        """
        for sample in samples:
            self.evaluate_sample(
                original_messages=sample["original_messages"],
                compressed_summary=sample["compressed_summary"],
                structured_summary=sample.get("structured_summary"),
                user_id=sample.get("user_id", "eval_user"),
                force_group=sample.get("force_group"),
            )
        return self.ab.generate_report()


# ---------------------------------------------------------------------------
# 模拟数据生成（用于无 LLM 环境下的框架验证）
# ---------------------------------------------------------------------------

def generate_mock_samples(count: int = 30) -> list[dict[str, Any]]:
    """生成模拟样本用于框架验证.

    生产环境应使用真实对话数据。
    """
    samples: list[dict[str, Any]] = []
    for i in range(count):
        # 交替分配到 control / experiment 组
        force_group = (
            ExperimentConfig.EXPERIMENT_GROUP
            if i % 2 == 0
            else ExperimentConfig.CONTROL_GROUP
        )
        # 模拟原始对话
        original_messages = [
            {"role": "user", "content": "请帮我分析 Milvus 向量数据库在 2024 年的性能表现"},
            {"role": "assistant", "content": "Milvus 在 2024 年发布了 2.4 版本，QPS 提升了 30%"},
            {"role": "user", "content": "和 PostgreSQL 的 pgvector 扩展相比如何？"},
            {"role": "assistant", "content": "Milvus 在大规模场景下 QPS 优势明显，PostgreSQL 适合小数据量"},
        ]
        # 模拟压缩摘要（实验组）
        compressed_summary = (
            "已确认结论：Milvus 2.4 性能提升 30%\n"
            "关键实体：Milvus、PostgreSQL、pgvector、2024、QPS\n"
            "当前意图：向量数据库选型对比"
        )
        structured_summary = {
            "confirmed": ["Milvus 2.4 性能提升 30%"],
            "excluded": [],
            "pending": [],
            "entities": ["Milvus", "PostgreSQL", "pgvector", "2024", "QPS"],
            "intent": "向量数据库选型对比",
        }
        samples.append({
            "original_messages": original_messages,
            "compressed_summary": compressed_summary,
            "structured_summary": structured_summary,
            "user_id": f"mock_user_{i}",
            "force_group": force_group,
        })
    return samples


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI 入口：运行评估并输出报告."""
    parser = argparse.ArgumentParser(description="L2 概念摘要质量评估")
    parser.add_argument(
        "--samples", type=int, default=30,
        help="模拟样本数量（默认 30）",
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="报告输出文件路径（JSON），不指定则打印到 stdout",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        help="日志级别",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))

    evaluator = CompressionQualityEvaluator()
    samples = generate_mock_samples(args.samples)
    report = evaluator.evaluate_batch(samples)

    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report_json)
        logger.info("Report written to %s", args.output)
    else:
        print(report_json)

    # 输出验收结论
    print("\n" + "=" * 60)
    print("验收结论:")
    print(f"  AC-17 (压缩率 20%-30%, 实体保留率 ≥ 95%): "
          f"{'PASS' if report['acceptance']['AC-17']['passed'] else 'FAIL'}")
    print(f"  AC-19 (人工评分不低于基线 5%):              "
          f"{'PASS' if report['acceptance']['AC-19']['passed'] else 'FAIL'}")
    print(f"  总体: {'PASS' if report['overall_passed'] else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
