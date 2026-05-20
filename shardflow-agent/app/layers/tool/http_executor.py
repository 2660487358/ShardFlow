import asyncio
from typing import Any

import httpx


class ToolResult:
    def __init__(self, tool_name: str, success: bool, data: Any = None, error: str = ""):
        self.tool_name = tool_name
        self.success = success
        self.data = data
        self.error = error


class HttpExecutor:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def execute(self, tool_name: str, params: dict[str, Any], url: str = "") -> ToolResult:
        client = await self._get_client()
        try:
            if url:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return ToolResult(tool_name, True, resp.json())
            return ToolResult(tool_name, True, {"stub": f"Tool {tool_name} executed (no URL configured)"})
        except Exception as e:
            return ToolResult(tool_name, False, error=str(e))

    async def execute_parallel(self, calls: list[tuple[str, dict[str, Any], str]]) -> list[ToolResult]:
        tasks = [self.execute(name, params, url) for name, params, url in calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if isinstance(r, ToolResult) else ToolResult("unknown", False, error=str(r))
            for r in results
        ]

    async def execute_with_retry(self, tool_name: str, params: dict[str, Any],
                                 url: str = "", retries: int = 3) -> ToolResult:
        last_result: ToolResult | None = None
        for attempt in range(retries + 1):
            result = await self.execute(tool_name, params, url)
            if result.success:
                return result
            last_result = result
            if attempt < retries:
                await asyncio.sleep(1.0 * (2 ** attempt))
        return last_result or ToolResult(tool_name, False, error="Max retries exceeded")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


http_executor = HttpExecutor()
