from typing import Any


def create_initial_state(
    task_id: str,
    tenant_id: str,
    session_id: str,
    user_input: str,
    max_rounds: int = 15,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "tenant_id": tenant_id,
        "session_id": session_id,
        "messages": [],
        "user_input": user_input,
        "intent": None,
        "entities": None,
        "think_result": None,
        "action_plan": None,
        "observation": None,
        "token_count": 0,
        "context_usage_ratio": 0.0,
        "should_shard": False,
        "loop_count": 0,
        "final_answer": None,
        "is_done": False,
        "error": None,
        "max_rounds": max_rounds,
    }
