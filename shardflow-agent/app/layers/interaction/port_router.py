"""L1 Interaction Layer: PortRouter — 端口标识解析与跨端口会话映射。

支持四种端口:
- web: Web 浏览器界面
- feishu: 飞书消息端口
- dingtalk: 钉钉消息端口
- cli: 命令行端口

核心功能:
1. 从 X-Port Header 解析端口类型
2. 维护端口→会话映射
3. 跨端口查找用户活跃会话
4. 按端口类型适配响应格式
"""
import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PortType(str, Enum):
    WEB = "web"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    CLI = "cli"
    UNKNOWN = "unknown"


class SessionMapping:
    """端口 → 会话映射记录。"""
    def __init__(self, user_id: str, session_id: str, port: PortType, task_id: str = ""):
        self.user_id = user_id
        self.session_id = session_id
        self.port = port
        self.task_id = task_id


class PortRouter:
    """端口路由器 — 识别接入端口并管理跨端口会话关联。"""

    # 端口类型识别规则
    PORT_HEADERS: dict[str, PortType] = {
        "web": PortType.WEB,
        "feishu": PortType.FEISHU,
        "dingtalk": PortType.DINGTALK,
        "cli": PortType.CLI,
    }

    def __init__(self) -> None:
        # 端口 → 活跃会话映射: {user_id:port -> SessionMapping}
        self._port_sessions: dict[str, SessionMapping] = {}

    def parse_port(self, x_port: str) -> PortType:
        """从 X-Port Header 解析端口类型。"""
        if not x_port:
            return PortType.UNKNOWN
        port_lower = x_port.strip().lower()
        return self.PORT_HEADERS.get(port_lower, PortType.UNKNOWN)

    def map_session(self, user_id: str, session_id: str, port: PortType,
                    task_id: str = "") -> SessionMapping:
        """建立端口 → 会话映射。"""
        key = self._port_key(user_id, port)
        mapping = SessionMapping(user_id, session_id, port, task_id)
        self._port_sessions[key] = mapping
        logger.info(f"Session mapped: user={user_id}, port={port.value}, session={session_id}")
        return mapping

    def find_active_session(self, user_id: str, port: PortType) -> SessionMapping | None:
        """在指定端口查找活跃会话。"""
        key = self._port_key(user_id, port)
        return self._port_sessions.get(key)

    def find_any_active_session(self, user_id: str) -> SessionMapping | None:
        """跨所有端口查找用户活跃会话（用于续接）。"""
        for port in PortType:
            if port == PortType.UNKNOWN:
                continue
            session = self.find_active_session(user_id, port)
            if session:
                return session
        return None

    def remove_session(self, user_id: str, port: PortType) -> None:
        """移除端口会话映射。"""
        key = self._port_key(user_id, port)
        self._port_sessions.pop(key, None)

    def adapt_response(self, port: PortType, content: str,
                       max_length: int = 0) -> str:
        """按端口类型适配响应内容格式。

        - web: 保持原始 Markdown 格式
        - feishu: 飞书消息限制（富文本/Markdown 卡片）
        - dingtalk: 钉钉消息限制（Markdown 简化）
        - cli: 纯文本终端输出
        """
        if port == PortType.WEB:
            return content

        if port in (PortType.FEISHU, PortType.DINGTALK):
            # 消息端口截断过长内容
            limit = max_length or 4096
            if len(content) > limit:
                content = content[:limit - 50] + "\n\n...(内容过长，请到 Web 端查看完整回复)"
            return content

        if port == PortType.CLI:
            # CLI 端口显示纯文本
            return content

        return content

    def _port_key(self, user_id: str, port: PortType) -> str:
        return f"{user_id}:{port.value}"


port_router = PortRouter()
