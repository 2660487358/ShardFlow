"""L5 Tool Execution: BuiltinTools — 内置工具注册与本地执行。

P6 阶段实现 (FR-BUILTIN-001, FR-BUILTIN-002):
- 内置工具在 Python 推理层启动时自动加载
- 与 MCP 工具统一发现和调用接口（MCPToolInfo 数据结构）
- 内置工具不走 MCP Server 远程调用，本地直接执行
- 内置工具的元数据由 Java 端 BuiltinToolInitializer 注册到 MCP 注册中心

内置工具列表:
- web_search: 联网搜索（委托给 web_searcher）
- read_file: 读取文件（HTTP 代理到 Java）
- write_file: 写入文件（HTTP 代理到 Java）
- code_analyze: 代码分析（HTTP 代理到 Java）
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class BuiltinToolHandler:
    """内置工具执行处理器。"""
    tool_name: str
    handler: Callable[..., Awaitable[dict[str, Any]]]
    description: str = ""


class BuiltinToolRegistry:
    """内置工具注册中心 — 管理内置工具的本地执行处理器。

    与 MCPClient 统一接口：
    - 内置工具通过 MCPToolInfo 发现（从 Java 注册中心获取）
    - 调用时通过 tool_type=BUILTIN 判断走本地执行路径
    - 不再硬编码工具元数据（符合 AR-5 红线）
    """

    def __init__(self) -> None:
        self._handlers: dict[str, BuiltinToolHandler] = {}

    def register_handler(self, handler: BuiltinToolHandler) -> None:
        """注册内置工具执行处理器。"""
        self._handlers[handler.tool_name] = handler
        logger.debug(f"Registered builtin tool handler: {handler.tool_name}")

    def get_handler(self, tool_name: str) -> BuiltinToolHandler | None:
        """获取内置工具执行处理器。"""
        return self._handlers.get(tool_name)

    def has_handler(self, tool_name: str) -> bool:
        """检查是否有内置工具执行处理器。"""
        return tool_name in self._handlers

    def list_handlers(self) -> list[str]:
        """列出所有已注册的内置工具名称。"""
        return list(self._handlers.keys())

    async def execute(self, tool_name: str, params: dict[str, Any],
                      _skip_security: bool = False) -> dict[str, Any]:
        """执行内置工具（内部接口，应通过 MCPClient.call_tool() 调用）。

        Args:
            tool_name: 工具名称
            params: 调用参数
            _skip_security: 内部参数，仅 MCPClient 调用时跳过安全网关

        Returns:
            工具执行结果

        Raises:
            KeyError: 工具未注册
            PermissionError: 绕过安全网关直接调用
        """
        # SEC-TOOL-001/002: 防止绕过安全网关直接调用
        if not _skip_security:
            logger.warning(
                f"Direct call to builtin tool '{tool_name}' bypassed security gateway. "
                "Use MCPClient.call_tool() instead."
            )
            raise PermissionError(
                f"内置工具 '{tool_name}' 不允许直接调用，请通过 MCPClient.call_tool() 调用"
            )
        handler = self._handlers.get(tool_name)
        if handler is None:
            raise KeyError(f"Builtin tool handler not found: {tool_name}")
        return await handler.handler(params)


# 全局单例
builtin_tool_registry = BuiltinToolRegistry()


# ======================== 内置工具执行处理器 ========================

async def _handle_web_search(params: dict[str, Any]) -> dict[str, Any]:
    """web_search 内置工具执行：委托给 web_searcher。"""
    try:
        from app.layers.retrieval.web_searcher import web_searcher
        query = params.get("query", "")
        max_results = params.get("max_results", 5)
        results = await web_searcher.search(query, max_results=max_results)
        return {
            "tool_name": "web_search",
            "content": results,
        }
    except Exception as e:
        logger.error(f"web_search execution failed: {e}")
        return {
            "tool_name": "web_search",
            "content": f"搜索失败: {str(e)[:200]}",
            "error": True,
        }


async def _handle_read_file(params: dict[str, Any]) -> dict[str, Any]:
    """read_file 内置工具执行：HTTP 代理到 Java 服务。"""
    try:
        import httpx
        from app.config import settings

        path = params.get("path", "")
        encoding = params.get("encoding", "utf-8")

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{settings.java_base_url}/api/v1/builtin/read-file",
                json={"path": path, "encoding": encoding},
                headers={"X-API-Key": settings.java_api_key or settings.llm_api_key},
            )
            resp.raise_for_status()
            return {
                "tool_name": "read_file",
                "content": resp.json().get("data", {}),
            }
    except Exception as e:
        logger.error(f"read_file execution failed: {e}")
        return {
            "tool_name": "read_file",
            "content": f"读取文件失败: {str(e)[:200]}",
            "error": True,
        }


async def _handle_write_file(params: dict[str, Any]) -> dict[str, Any]:
    """write_file 内置工具执行：HTTP 代理到 Java 服务。"""
    try:
        import httpx
        from app.config import settings

        path = params.get("path", "")
        content = params.get("content", "")
        encoding = params.get("encoding", "utf-8")

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            resp = await client.post(
                f"{settings.java_base_url}/api/v1/builtin/write-file",
                json={"path": path, "content": content, "encoding": encoding},
                headers={"X-API-Key": settings.java_api_key or settings.llm_api_key},
            )
            resp.raise_for_status()
            return {
                "tool_name": "write_file",
                "content": resp.json().get("data", {}),
            }
    except Exception as e:
        logger.error(f"write_file execution failed: {e}")
        return {
            "tool_name": "write_file",
            "content": f"写入文件失败: {str(e)[:200]}",
            "error": True,
        }


async def _handle_code_analyze(params: dict[str, Any]) -> dict[str, Any]:
    """code_analyze 内置工具执行：HTTP 代理到 Java 服务。"""
    try:
        import httpx
        from app.config import settings

        path = params.get("path", "")
        query = params.get("query", "")

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{settings.java_base_url}/api/v1/builtin/code-analyze",
                json={"path": path, "query": query},
                headers={"X-API-Key": settings.java_api_key or settings.llm_api_key},
            )
            resp.raise_for_status()
            return {
                "tool_name": "code_analyze",
                "content": resp.json().get("data", {}),
            }
    except Exception as e:
        logger.error(f"code_analyze execution failed: {e}")
        return {
            "tool_name": "code_analyze",
            "content": f"代码分析失败: {str(e)[:200]}",
            "error": True,
        }


def _register_builtin_handlers() -> None:
    """注册所有内置工具执行处理器。"""
    builtin_tool_registry.register_handler(
        BuiltinToolHandler(tool_name="web_search", handler=_handle_web_search,
                          description="联网搜索：通过搜索引擎获取最新信息")
    )
    builtin_tool_registry.register_handler(
        BuiltinToolHandler(tool_name="read_file", handler=_handle_read_file,
                          description="读取指定文件内容")
    )
    builtin_tool_registry.register_handler(
        BuiltinToolHandler(tool_name="write_file", handler=_handle_write_file,
                          description="写入文件内容")
    )
    builtin_tool_registry.register_handler(
        BuiltinToolHandler(tool_name="code_analyze", handler=_handle_code_analyze,
                          description="代码静态分析和语义理解")
    )
    logger.info(f"Registered {len(builtin_tool_registry.list_handlers())} builtin tool handlers")


# 模块加载时自动注册
_register_builtin_handlers()
