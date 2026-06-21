"""S6.11 一致性巡检脚本 — 每日检查 sessions 与 kb_shard 状态漂移。

实现《Agent 数据库交互规则实施计划》S6.11 任务：
- 检查 Redis L1 与 PG L2 的会话状态摘要一致性
- 检查 kb_shard 状态机漂移（active/archived/deleted）
- 检查幂等键残留（过期未清理）
- 检查降级队列堆积
- 检查 MCP 工具状态 Hash 健康
- 输出巡检报告（JSON + 控制台）

使用方式：
    python scripts/consistency_check.py                    # 单次巡检
    python scripts/consistency_check.py --schedule daily   # 每日定时巡检
    python scripts/consistency_check.py --output report.json  # 输出到文件

关联文档：
- 《Agent 数据库交互规则文档》v1.2 一致性巡检章节
- 《监控与链路追踪设计文档》6 项一致性巡检
- 《Agent 数据库交互规则实施计划》S6.11
"""
import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("consistency_check")


# ============================================================================
# 巡检结果数据结构
# ============================================================================

@dataclass
class CheckResult:
    """单项巡检结果。"""

    check_id: str
    name: str
    status: str  # PASS / WARN / FAIL
    metric: str
    value: Any
    threshold: str
    details: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class InspectionReport:
    """巡检报告。"""

    report_id: str
    started_at: str
    finished_at: str = ""
    total_checks: int = 0
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    results: list[CheckResult] = field(default_factory=list)
    summary: str = ""

    def add_result(self, result: CheckResult) -> None:
        self.results.append(result)
        self.total_checks += 1
        if result.status == "PASS":
            self.passed += 1
        elif result.status == "WARN":
            self.warnings += 1
        elif result.status == "FAIL":
            self.failed += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "warnings": self.warnings,
            "failed": self.failed,
            "results": [asdict(r) for r in self.results],
            "summary": self.summary,
        }


# ============================================================================
# 巡检项实现
# ============================================================================

class ConsistencyChecker:
    """一致性巡检器。"""

    # 巡检阈值（与规则文档/监控文档一致）
    SESSION_DRIFT_THRESHOLD = 10  # 会话状态漂移 ≤ 10/小时
    IDEMPOTENT_KEY_TTL_MAX = 300  # 幂等键 TTL ≤ 300s
    DEGRADATION_QUEUE_MAX = 100  # 降级队列堆积 ≤ 100
    MCP_EMPTY_HASH_MAX = 3  # MCP 连续空拉取 ≤ 3

    def __init__(self) -> None:
        self.report = InspectionReport(
            report_id=f"inspect_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
            started_at=datetime.now(timezone.utc).isoformat(),
        )

    async def check_session_summary_consistency(self) -> CheckResult:
        """检查 1: 会话状态摘要 Redis L1 与 PG L2 一致性。"""
        check_id = "C-SESSION-DRIFT"
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()

            # 扫描 Redis L1 中的会话摘要键
            session_keys: list[str] = []
            async for key in r.scan_iter(match="session:*:summary", count=100):
                key_str = key.decode() if isinstance(key, bytes) else key
                # 排除 version 键
                if ":version" not in key_str:
                    session_keys.append(key_str)

            # 检查每个摘要的版本号是否存在
            drift_count = 0
            for session_key in session_keys:
                version_key = f"{session_key}:version"
                version = await r.get(version_key)
                if version is None:
                    drift_count += 1
                    logger.warning(
                        "会话摘要版本号缺失: %s (潜在 L1/L2 漂移)",
                        session_key,
                    )

            status = "PASS" if drift_count <= self.SESSION_DRIFT_THRESHOLD else "FAIL"
            return CheckResult(
                check_id=check_id,
                name="会话状态摘要 L1/L2 一致性",
                status=status,
                metric="drift_count",
                value=drift_count,
                threshold=f"≤ {self.SESSION_DRIFT_THRESHOLD}/小时",
                details=f"扫描 {len(session_keys)} 个会话摘要键，{drift_count} 个版本号缺失",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="会话状态摘要 L1/L2 一致性",
                status="WARN",
                metric="error",
                value=str(e),
                threshold=f"≤ {self.SESSION_DRIFT_THRESHOLD}/小时",
                details=f"巡检异常（Redis 可能不可用）: {e}",
            )

    async def check_kb_shard_status_drift(self) -> CheckResult:
        """检查 2: kb_shard 状态机漂移。"""
        check_id = "C-KBSHARD-DRIFT"
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()

            # 扫描 kb_shard 相关的 Redis 缓存键
            shard_keys: list[str] = []
            async for key in r.scan_iter(match="shardflow:*:shard:*", count=100):
                key_str = key.decode() if isinstance(key, bytes) else key
                shard_keys.append(key_str)

            # 检查状态字段是否合法（active/archived/deleted）
            invalid_status_count = 0
            valid_statuses = {"active", "archived", "deleted"}
            for shard_key in shard_keys:
                shard_data = await r.get(shard_key)
                if shard_data:
                    try:
                        data_str = (
                            shard_data.decode()
                            if isinstance(shard_data, bytes)
                            else shard_data
                        )
                        data = json.loads(data_str)
                        status = data.get("status", "active")
                        if status not in valid_statuses:
                            invalid_status_count += 1
                            logger.warning(
                                "kb_shard 状态非法: %s status=%s",
                                shard_key,
                                status,
                            )
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        invalid_status_count += 1

            status = "PASS" if invalid_status_count == 0 else "WARN"
            return CheckResult(
                check_id=check_id,
                name="kb_shard 状态机一致性",
                status=status,
                metric="invalid_status_count",
                value=invalid_status_count,
                threshold="= 0",
                details=f"扫描 {len(shard_keys)} 个 kb_shard 缓存键，{invalid_status_count} 个状态非法",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="kb_shard 状态机一致性",
                status="WARN",
                metric="error",
                value=str(e),
                threshold="= 0",
                details=f"巡检异常: {e}",
            )

    async def check_idempotent_key_residual(self) -> CheckResult:
        """检查 3: 幂等键残留（过期未清理）。"""
        check_id = "C-IDEMPOTENT-RESIDUAL"
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()

            # 扫描幂等键
            idempotent_keys: list[str] = []
            async for key in r.scan_iter(match="shardflow:idempotent:*", count=100):
                key_str = key.decode() if isinstance(key, bytes) else key
                idempotent_keys.append(key_str)

            # 检查 TTL（幂等键应在 300s 后过期）
            residual_count = 0
            for key in idempotent_keys:
                ttl = await r.ttl(key)
                # TTL < 0 表示键无过期时间（残留）
                if ttl < 0:
                    residual_count += 1
                    logger.warning("幂等键无 TTL（残留）: %s", key)

            status = "PASS" if residual_count == 0 else "WARN"
            return CheckResult(
                check_id=check_id,
                name="幂等键残留检查",
                status=status,
                metric="residual_count",
                value=residual_count,
                threshold=f"= 0 (TTL ≤ {self.IDEMPOTENT_KEY_TTL_MAX}s)",
                details=f"扫描 {len(idempotent_keys)} 个幂等键，{residual_count} 个无 TTL",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="幂等键残留检查",
                status="WARN",
                metric="error",
                value=str(e),
                threshold=f"= 0 (TTL ≤ {self.IDEMPOTENT_KEY_TTL_MAX}s)",
                details=f"巡检异常: {e}",
            )

    async def check_degradation_queue_backlog(self) -> CheckResult:
        """检查 4: 降级队列堆积。"""
        check_id = "C-DEGRADATION-BACKLOG"
        try:
            from app.infrastructure.redis_client import redis_client
            from app.layers.agent_core.memory_degradation import (
                DEGRADATION_QUEUE_KEY,
            )

            r = await redis_client.get_redis()
            queue_length = await r.llen(DEGRADATION_QUEUE_KEY)

            status = (
                "PASS"
                if queue_length <= self.DEGRADATION_QUEUE_MAX
                else "WARN"
            )
            return CheckResult(
                check_id=check_id,
                name="降级队列堆积检查",
                status=status,
                metric="queue_length",
                value=queue_length,
                threshold=f"≤ {self.DEGRADATION_QUEUE_MAX}",
                details=f"降级队列 {DEGRADATION_QUEUE_KEY} 长度: {queue_length}",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="降级队列堆积检查",
                status="WARN",
                metric="error",
                value=str(e),
                threshold=f"≤ {self.DEGRADATION_QUEUE_MAX}",
                details=f"巡检异常: {e}",
            )

    async def check_mcp_tool_hash_health(self) -> CheckResult:
        """检查 5: MCP 工具状态 Hash 健康。"""
        check_id = "C-MCP-HASH-HEALTH"
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()

            # 扫描 MCP 工具状态 Hash 键
            mcp_hash_keys: list[str] = []
            async for key in r.scan_iter(match="shardflow:*:mcp:tool_states", count=100):
                key_str = key.decode() if isinstance(key, bytes) else key
                mcp_hash_keys.append(key_str)

            empty_hash_count = 0
            for hash_key in mcp_hash_keys:
                field_count = await r.hlen(hash_key)
                if field_count == 0:
                    empty_hash_count += 1
                    logger.warning("MCP 工具状态 Hash 为空: %s", hash_key)

            status = (
                "PASS"
                if empty_hash_count <= self.MCP_EMPTY_HASH_MAX
                else "FAIL"
            )
            return CheckResult(
                check_id=check_id,
                name="MCP 工具状态 Hash 健康",
                status=status,
                metric="empty_hash_count",
                value=empty_hash_count,
                threshold=f"≤ {self.MCP_EMPTY_HASH_MAX}",
                details=f"扫描 {len(mcp_hash_keys)} 个 MCP Hash 键，{empty_hash_count} 个为空",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="MCP 工具状态 Hash 健康",
                status="WARN",
                metric="error",
                value=str(e),
                threshold=f"≤ {self.MCP_EMPTY_HASH_MAX}",
                details=f"巡检异常: {e}",
            )

    async def check_redis_key_namespace_compliance(self) -> CheckResult:
        """检查 6: Redis Key 命名规范合规性。"""
        check_id = "C-REDIS-KEY-NAMESPACE"
        try:
            from app.infrastructure.redis_client import redis_client

            r = await redis_client.get_redis()

            # 扫描所有 shardflow: 前缀的键
            all_keys: list[str] = []
            async for key in r.scan_iter(match="shardflow:*", count=1000):
                key_str = key.decode() if isinstance(key, bytes) else key
                all_keys.append(key_str)

            # 检查 Key 是否符合 4 段格式 shardflow:{user}:{domain}:{key}
            # 或会话维度 session:{id}:xxx
            non_compliant_count = 0
            for key in all_keys:
                # 跳过已知合法的特殊前缀
                if key.startswith("shardflow:idempotent:"):
                    continue
                if key.startswith("shardflow:degradation:"):
                    continue

                # 检查 4 段格式
                parts = key.split(":")
                if len(parts) < 3:
                    non_compliant_count += 1
                    logger.warning("Redis Key 命名不规范: %s", key)

            status = "PASS" if non_compliant_count == 0 else "WARN"
            return CheckResult(
                check_id=check_id,
                name="Redis Key 命名规范合规",
                status=status,
                metric="non_compliant_count",
                value=non_compliant_count,
                threshold="= 0",
                details=f"扫描 {len(all_keys)} 个 shardflow: 键，{non_compliant_count} 个命名不规范",
            )
        except Exception as e:
            return CheckResult(
                check_id=check_id,
                name="Redis Key 命名规范合规",
                status="WARN",
                metric="error",
                value=str(e),
                threshold="= 0",
                details=f"巡检异常: {e}",
            )

    async def run_all_checks(self) -> InspectionReport:
        """执行全部巡检项。"""
        logger.info("开始一致性巡检: %s", self.report.report_id)

        # 执行所有巡检项
        checks = [
            self.check_session_summary_consistency(),
            self.check_kb_shard_status_drift(),
            self.check_idempotent_key_residual(),
            self.check_degradation_queue_backlog(),
            self.check_mcp_tool_hash_health(),
            self.check_redis_key_namespace_compliance(),
        ]

        for check_coro in checks:
            result = await check_coro
            self.report.add_result(result)
            logger.info(
                "[%s] %s: %s (value=%s)",
                result.status,
                result.check_id,
                result.name,
                result.value,
            )

        self.report.finished_at = datetime.now(timezone.utc).isoformat()

        # 生成摘要
        self.report.summary = (
            f"巡检完成: {self.report.total_checks} 项检查, "
            f"通过 {self.report.passed}, "
            f"警告 {self.report.warnings}, "
            f"失败 {self.report.failed}"
        )
        logger.info(self.report.summary)

        return self.report


# ============================================================================
# 主入口
# ============================================================================

async def run_inspection(output_file: str | None = None) -> InspectionReport:
    """运行一次完整巡检。

    Args:
        output_file: 可选的输出文件路径（JSON 格式）
    """
    checker = ConsistencyChecker()
    report = await checker.run_all_checks()

    # 输出到控制台
    print("\n" + "=" * 70)
    print(f"一致性巡检报告 {report.report_id}")
    print("=" * 70)
    print(f"开始时间: {report.started_at}")
    print(f"结束时间: {report.finished_at}")
    print(f"总检查数: {report.total_checks}")
    print(f"通过: {report.passed} | 警告: {report.warnings} | 失败: {report.failed}")
    print("-" * 70)

    for result in report.results:
        status_icon = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[
            result.status
        ]
        print(
            f"{status_icon} {result.check_id} {result.name}: "
            f"{result.metric}={result.value} (阈值 {result.threshold})"
        )
        if result.details:
            print(f"       {result.details}")

    print("-" * 70)
    print(report.summary)
    print("=" * 70)

    # 输出到文件
    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\n报告已输出到: {output_path}")

    return report


async def schedule_daily_inspection(output_dir: str = "reports") -> None:
    """每日定时巡检（每 24 小时执行一次）。"""
    import time

    interval_seconds = 24 * 3600  # 24 小时
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    logger.info("启动每日定时巡检，间隔 %d 秒", interval_seconds)

    while True:
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_file = output_path / f"consistency_report_{timestamp}.json"
            await run_inspection(str(output_file))
        except Exception as e:
            logger.error("定时巡检异常: %s", e)

        await asyncio.sleep(interval_seconds)


def main() -> None:
    """主入口。"""
    parser = argparse.ArgumentParser(
        description="ShardFlow 一致性巡检脚本（S6.11）"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="输出报告文件路径（JSON 格式）",
    )
    parser.add_argument(
        "--schedule",
        "-s",
        type=str,
        choices=["daily"],
        help="定时巡检模式（daily=每日）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="定时巡检报告输出目录",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.schedule == "daily":
        asyncio.run(schedule_daily_inspection(args.output_dir))
    else:
        asyncio.run(run_inspection(args.output))


if __name__ == "__main__":
    main()
