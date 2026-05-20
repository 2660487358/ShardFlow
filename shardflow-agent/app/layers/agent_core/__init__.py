"""L2 Agent Core Layer — ReAct loop orchestration, LLM routing, context management."""

from app.layers.agent_core.context_manager import context_manager, ContextManager
from app.layers.agent_core.context_shard import context_shard_manager, ContextShardManager
from app.layers.agent_core.langgraph_engine import react_graph, build_react_graph
from app.layers.agent_core.llm_router import llm_router, LLMRouter
from app.layers.agent_core.prompt_engine import prompt_engine, PromptEngine
from app.layers.agent_core.shard_decision import shard_decision_gate, ShardDecisionGate
from app.layers.agent_core.strategy_engine import strategy_engine, StrategyEngine, DEFAULT_STRATEGIES

__all__ = [
    "context_manager", "ContextManager",
    "context_shard_manager", "ContextShardManager",
    "react_graph", "build_react_graph",
    "llm_router", "LLMRouter",
    "prompt_engine", "PromptEngine",
    "shard_decision_gate", "ShardDecisionGate",
    "strategy_engine", "StrategyEngine",
    "DEFAULT_STRATEGIES",
]
