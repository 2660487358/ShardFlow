from typing import Any

from app.models.search_result import ToolMetadata


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, tool: ToolMetadata) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolMetadata:
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return self._tools[name]

    def list_all(self) -> list[ToolMetadata]:
        return list(self._tools.values())

    def validate_input(self, tool_name: str, input_data: dict[str, Any]) -> bool:
        if tool_name not in self._tools:
            return False
        schema = self._tools[tool_name].input_schema
        if not schema:
            return True
        required = schema.get("required", [])
        return all(k in input_data for k in required)


tool_registry = ToolRegistry()


def _register_default_tools() -> None:
    defaults = [
        ToolMetadata(name="read_file", description="Read a file from the repository", permissions=["repo:read"]),
        ToolMetadata(name="search_code", description="Search code in the repository", permissions=["repo:read"]),
        ToolMetadata(name="query_source", description="Multi-source knowledge retrieval", permissions=["search:read"]),
        ToolMetadata(
            name="extract_shard",
            description="Extract context shard from conversation",
            permissions=["shard:write"],
        ),
        ToolMetadata(name="query_strategy", description="Query historical strategies", permissions=["strategy:read"]),
        ToolMetadata(name="save_strategy", description="Save a strategy record", permissions=["strategy:write"]),
    ]
    for tool in defaults:
        tool_registry.register(tool)


_register_default_tools()
