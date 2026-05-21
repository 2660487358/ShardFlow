"""L2 Agent Core Layer — ReAct loop orchestration, LLM routing, context management, and memory interface.

The Memory Interface Layer (新增) provides unified abstraction for all memory read/write
operations, shielding upper-level code from storage backend differences.
"""
from app.layers.agent_core.context_manager import context_manager, ContextManager
from app.layers.agent_core.context_shard import context_shard_manager, ContextShardManager
from app.layers.agent_core.langgraph_engine import react_graph, build_react_graph
from app.layers.agent_core.llm_router import llm_router, LLMRouter
from app.layers.agent_core.prompt_engine import prompt_engine, PromptEngine
from app.layers.agent_core.shard_decision import shard_decision_gate, ShardDecisionGate
from app.layers.agent_core.strategy_engine import strategy_engine, StrategyEngine, DEFAULT_STRATEGIES

# Memory Interface Layer (new)
from app.layers.agent_core.memory_interface import MemoryStore, MemoryStoreFactory
from app.layers.agent_core.memory_orchestrator import memory_orchestrator, MemoryOrchestrator
from app.layers.agent_core.memory_lifecycle import memory_lifecycle, MemoryLifecycle
from app.layers.agent_core.memory_consistency import memory_consistency, MemoryConsistency
from app.layers.agent_core.memory_degradation import memory_degradation, MemoryDegradation
from app.layers.agent_core.memory_events import memory_events, MemoryEvents
from app.layers.agent_core.memory_adapters import (
    L0CacheAdapter, RedisAdapter, JavaAPIAdapter, CompositeAdapter,
)

__all__ = [
    # Original modules
    "context_manager", "ContextManager",
    "context_shard_manager", "ContextShardManager",
    "react_graph", "build_react_graph",
    "llm_router", "LLMRouter",
    "prompt_engine", "PromptEngine",
    "shard_decision_gate", "ShardDecisionGate",
    "strategy_engine", "StrategyEngine",
    "DEFAULT_STRATEGIES",
    # Memory Interface Layer
    "MemoryStore", "MemoryStoreFactory",
    "memory_orchestrator", "MemoryOrchestrator",
    "memory_lifecycle", "MemoryLifecycle",
    "memory_consistency", "MemoryConsistency",
    "memory_degradation", "MemoryDegradation",
    "memory_events", "MemoryEvents",
    "L0CacheAdapter", "RedisAdapter", "JavaAPIAdapter", "CompositeAdapter",
]
