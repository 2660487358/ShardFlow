"""L2 Agent Core: SkillArtifactLoader — Artifact 加载器（L3 MinIO 回源）。

Per Skills管理需求规格文档 FR-9.3 / FR-8.6 / 实施计划 P5.5.

职责：
- 从 MinIO 加载 Skill Artifact（prompt.md / tool.py / workflow.yaml / skill.json / manifest.json）
- 支持预签名 URL 直接下载（避免 Java 中转）
- 加载超时控制（可配置，默认 10s）
- 与 SkillCache 配合：缓存未命中时回源
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import settings
from app.models.skill import SkillMeta

logger = logging.getLogger(__name__)


class SkillArtifactLoader:
    """Artifact 加载器。

    加载策略：
    1. 优先从 Java 后端获取预签名 URL（GET /api/v1/skills/{skill_code}/artifacts/presign）
    2. 通过预签名 URL 直接从 MinIO 下载 Artifact 内容
    3. 加载超时控制（单文件默认 10s）
    """

    DEFAULT_TIMEOUT: float = 10.0  # 单文件加载超时
    MAX_ARTIFACT_SIZE: int = 10 * 1024 * 1024  # 10MB（与 NFR-5.1 一致）

    def __init__(self) -> None:
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(self.DEFAULT_TIMEOUT))
        return self._http_client

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def load_artifact(
        self,
        skill: SkillMeta,
        artifact_type: str,
        timeout: float | None = None,
    ) -> str | None:
        """加载指定类型的 Artifact 内容。

        Args:
            skill: Skill 元数据
            artifact_type: prompt_md | tool_py | workflow_yaml | skill_json | manifest_json
            timeout: 加载超时（秒），默认 DEFAULT_TIMEOUT

        Returns:
            Artifact 文本内容，失败返回 None
        """
        timeout = timeout or self.DEFAULT_TIMEOUT
        start_ts = time.monotonic()

        try:
            # 1. 获取预签名 URL
            presign_url = await self._get_presign_url(skill, artifact_type)
            if not presign_url:
                logger.warning(
                    f"Failed to get presign URL for skill={skill.skill_code} "
                    f"artifact={artifact_type}"
                )
                return None

            # 2. 下载 Artifact 内容（带超时控制）
            content = await asyncio.wait_for(
                self._download_artifact(presign_url, timeout),
                timeout=timeout,
            )
            if content is None:
                return None

            elapsed = time.monotonic() - start_ts
            logger.info(
                f"SkillArtifactLoader: loaded skill={skill.skill_code} "
                f"artifact={artifact_type} size={len(content)} elapsed={elapsed:.3f}s"
            )
            return content

        except asyncio.TimeoutError:
            logger.warning(
                f"SkillArtifactLoader: timeout skill={skill.skill_code} "
                f"artifact={artifact_type} timeout={timeout}s"
            )
            return None
        except Exception as e:
            logger.warning(
                f"SkillArtifactLoader: failed skill={skill.skill_code} "
                f"artifact={artifact_type} error={e}"
            )
            return None

    async def load_prompt_md(self, skill: SkillMeta, timeout: float | None = None) -> str | None:
        """加载 prompt.md 内容。"""
        return await self.load_artifact(skill, "prompt_md", timeout)

    async def load_tool_py(self, skill: SkillMeta, timeout: float | None = None) -> str | None:
        """加载 tool.py 内容。"""
        return await self.load_artifact(skill, "tool_py", timeout)

    async def load_workflow_yaml(self, skill: SkillMeta, timeout: float | None = None) -> str | None:
        """加载 workflow.yaml 内容。"""
        return await self.load_artifact(skill, "workflow_yaml", timeout)

    async def load_skill_json(self, skill: SkillMeta, timeout: float | None = None) -> dict[str, Any] | None:
        """加载 skill.json 内容。"""
        import json

        content = await self.load_artifact(skill, "skill_json", timeout)
        if content is None:
            return None
        try:
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to parse skill.json: {e}")
            return None

    async def load_manifest_json(self, skill: SkillMeta, timeout: float | None = None) -> dict[str, Any] | None:
        """加载 manifest.json 内容。"""
        import json

        content = await self.load_artifact(skill, "manifest_json", timeout)
        if content is None:
            return None
        try:
            return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to parse manifest.json: {e}")
            return None

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    async def _get_presign_url(self, skill: SkillMeta, artifact_type: str) -> str | None:
        """从 Java 后端获取 Artifact 预签名 URL。"""
        # 优先从 SkillMeta.artifacts 取本地缓存路径
        if skill.artifacts and artifact_type in skill.artifacts:
            return skill.artifacts[artifact_type]

        # 调用 Java 后端获取预签名 URL
        base_url = settings.java_base_url
        api_key = settings.java_api_key or settings.llm_api_key
        headers = {"X-API-Key": api_key, "X-User-Id": skill.user_id}

        try:
            client = await self._get_client()
            resp = await client.get(
                f"{base_url}/api/v1/skills/{skill.skill_code}/artifacts/presign",
                headers=headers,
                params={"artifact_type": artifact_type, "version": skill.current_version},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("url")
        except Exception as e:
            logger.warning(f"Failed to get presign URL: {e}")
            return None

    async def _download_artifact(self, url: str, timeout: float) -> str | None:
        """通过预签名 URL 下载 Artifact 内容。"""
        try:
            client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.text
                if len(content) > self.MAX_ARTIFACT_SIZE:
                    logger.warning(
                        f"Artifact size {len(content)} exceeds limit {self.MAX_ARTIFACT_SIZE}"
                    )
                    return None
                return content
            finally:
                await client.aclose()
        except Exception as e:
            logger.warning(f"Failed to download artifact: {e}")
            return None


# 模块级单例
skill_artifact_loader = SkillArtifactLoader()
