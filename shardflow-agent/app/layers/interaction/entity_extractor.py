import re
from typing import Any


class EntityExtractor:
    """Extracts entities from user input using regex rules and keyword matching.

    通用实体提取 — 覆盖代码实体 + 个人助手场景实体：
    - 代码实体: tech_stack, file_path, service, module, version, project
    - 通用实体: date, time, person, location, task_item, calendar_event, doc_ref
    """

    # ---- 代码实体（保留） ----
    TECH_STACK: set[str] = {
        "dubbo", "spring", "spring boot", "spring cloud", "redis", "kafka",
        "mysql", "postgresql", "mongodb", "nacos", "zookeeper", "docker",
        "kubernetes", "k8s", "nginx", "gateway", "mybatis", "hibernate",
        "grpc", "thrift", "rabbitmq", "elasticsearch", "flink", "spark",
    }

    FILE_PATTERN: re.Pattern[str] = re.compile(
        r"(?:[a-zA-Z0-9_\-]+/)*[a-zA-Z0-9_\-]+\.(?:java|py|go|ts|js|tsx|jsx|yaml|yml|xml|json|proto)",
        re.IGNORECASE,
    )

    VERSION_PATTERN: re.Pattern[str] = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9]+)?)\b")

    SERVICE_PATTERN: re.Pattern[str] = re.compile(
        r"\b([A-Z][a-zA-Z]*(?:Service|Controller|Repository|Manager|Handler|Gateway|Client))\b"
    )

    PROJECT_PATTERN: re.Pattern[str] = re.compile(
        r"\b([A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*(?:App|Service|Project|Module|System|Platform|Engine|Hub|Flow|Bridge|Agent|Portal|Center))\b"
    )

    MODULE_PATTERN: re.Pattern[str] = re.compile(
        r"\b([a-z][a-z0-9_]*\.(?:api|service|controller|repository|manager|handler|config|util|model|dto|vo|dao|mapper|common|core|infra|domain|gateway|client)s?)\b"
    )

    # ---- 通用实体（新增） ----

    # 日期模式：2024-01-15, 2024/01/15, 1月15日, 明天, 下周三, etc.
    DATE_PATTERN: re.Pattern[str] = re.compile(
        r"(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}"                # 2024-01-15
        r"|\d{1,2}月\d{1,2}[日号]"                          # 1月15日
        r"|(?:今天|明天|后天|昨天|前天)"                       # 相对日期
        r"|(?:下[个]?(?:周|星期)[一二三四五六日天])"            # 下周X
        r"|(?:本周[一二三四五六日天])"                          # 本周X
        r"|(?:下个?月\d{1,2}[日号]?)"                         # 下个月15日
        r")",
        re.IGNORECASE,
    )

    # 时间模式：14:30, 下午3点, 3pm, etc.
    TIME_PATTERN: re.Pattern[str] = re.compile(
        r"(?:\d{1,2}:\d{2}(?::\d{2})?"                     # 14:30
        r"|(?:早上|上午|中午|下午|晚上|傍晚)?\d{1,2}[点时](?:半|整|钟)?"  # 下午3点
        r"|\d{1,2}(?:am|pm|AM|PM))",                        # 3pm
        re.IGNORECASE,
    )

    # 人名模式（中英文）
    PERSON_PATTERN: re.Pattern[str] = re.compile(
        r"(?:@[a-zA-Z0-9_]+"                                # @username
        r"|[A-Z][a-z]+ [A-Z][a-z]+"                         # English name
        r"|[一-鿿]{2,4}(?:老师|先生|女士|经理|总监|总|工)?)"  # 中文名+称谓
    )

    # 地点/组织
    LOCATION_PATTERN: re.Pattern[str] = re.compile(
        r"(?:北京|上海|广州|深圳|杭州|成都|南京|武汉|西安"
        r"|会议室[0-9A-Za-z]*|[一-鿿]+大厦|[一-鿿]+园区"
        r"|[一-鿿]+会议室|[一-鿿]+办公室)"
    )

    # 任务项：TODO/FIXME/HACK/XXX 标记
    TASK_ITEM_PATTERN: re.Pattern[str] = re.compile(
        r"(?:TODO|FIXME|HACK|XXX|NOTE|OPTIMIZE)[: ]*(.+?)(?:\n|$)",
        re.IGNORECASE,
    )

    # 日历事件关键词
    CALENDAR_EVENT_PATTERN: re.Pattern[str] = re.compile(
        r"(?:会议|约会|面试|日程|提醒|待办|截止|deadline|meeting|appointment)",
        re.IGNORECASE,
    )

    # 文档引用
    DOC_REF_PATTERN: re.Pattern[str] = re.compile(
        r"(?:https?://[^\s]+"                               # URL
        r"|[\w-]+\.(?:md|rst|txt|pdf|docx?)"               # 文档文件
        r"|(?:confluence|wiki|jira|notion)[^\s]*"          # 协作平台
        r"|(?:#\d+|\[[A-Z]+-\d+\]))",                       # issue/PR 编号
        re.IGNORECASE,
    )

    # ---- 提取入口 ----

    def extract(self, user_input: str) -> dict[str, list[str]]:
        entities: dict[str, list[str]] = {
            # 代码实体
            "project": [],
            "service": [],
            "tech_stack": [],
            "file_path": [],
            "module": [],
            "version": [],
            # 通用实体
            "date": [],
            "time": [],
            "person": [],
            "location": [],
            "task_item": [],
            "calendar_event": [],
            "doc_ref": [],
        }

        # 代码实体
        entities["tech_stack"] = self._extract_tech_stack(user_input)
        entities["service"] = self._extract_services(user_input)
        entities["file_path"] = self._extract_file_paths(user_input)
        entities["version"] = self._extract_versions(user_input)
        entities["project"] = self._extract_projects(user_input)
        entities["module"] = self._extract_modules(user_input)

        # 通用实体
        entities["date"] = self._extract_pattern(self.DATE_PATTERN, user_input)
        entities["time"] = self._extract_pattern(self.TIME_PATTERN, user_input)
        entities["person"] = self._extract_pattern(self.PERSON_PATTERN, user_input)
        entities["location"] = self._extract_pattern(self.LOCATION_PATTERN, user_input)
        entities["task_item"] = self._extract_pattern(self.TASK_ITEM_PATTERN, user_input)
        entities["calendar_event"] = self._extract_pattern(self.CALENDAR_EVENT_PATTERN, user_input)
        entities["doc_ref"] = self._extract_pattern(self.DOC_REF_PATTERN, user_input)

        return entities

    async def extract_async(self, user_input: str) -> dict[str, Any]:
        return self.extract(user_input)

    # ---- 辅助方法 ----

    def _extract_pattern(self, pattern: re.Pattern[str], text: str) -> list[str]:
        matches = pattern.findall(text)
        # Deduplicate while preserving order
        return list(dict.fromkeys(m.strip() if isinstance(m, str) else str(m[0] if isinstance(m, tuple) else m).strip() for m in matches))

    def _extract_tech_stack(self, text: str) -> list[str]:
        found: list[str] = []
        lower = text.lower()
        for tech in self.TECH_STACK:
            if tech in lower:
                found.append(tech)
        return found

    def _extract_services(self, text: str) -> list[str]:
        matches = self.SERVICE_PATTERN.findall(text)
        return list(set(matches))

    def _extract_file_paths(self, text: str) -> list[str]:
        matches = self.FILE_PATTERN.findall(text)
        return matches

    def _extract_versions(self, text: str) -> list[str]:
        matches = self.VERSION_PATTERN.findall(text)
        return matches

    def _extract_projects(self, text: str) -> list[str]:
        matches = self.PROJECT_PATTERN.findall(text)
        return list(dict.fromkeys(matches))

    def _extract_modules(self, text: str) -> list[str]:
        matches = self.MODULE_PATTERN.findall(text)
        return list(dict.fromkeys(matches))


entity_extractor = EntityExtractor()
