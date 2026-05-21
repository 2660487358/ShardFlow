import re
from typing import Any


class EntityExtractor:
    """Extracts entities from user input using regex rules and keyword matching."""

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

    def extract(self, user_input: str) -> dict[str, list[str]]:
        entities: dict[str, list[str]] = {
            "project": [],
            "service": [],
            "tech_stack": [],
            "file_path": [],
            "module": [],
            "version": [],
        }

        entities["tech_stack"] = self._extract_tech_stack(user_input)
        entities["service"] = self._extract_services(user_input)
        entities["file_path"] = self._extract_file_paths(user_input)
        entities["version"] = self._extract_versions(user_input)
        entities["project"] = self._extract_projects(user_input)
        entities["module"] = self._extract_modules(user_input)

        return entities

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

    async def extract_async(self, user_input: str) -> dict[str, Any]:
        return self.extract(user_input)

    PROJECT_PATTERN: re.Pattern[str] = re.compile(
        r"\b([A-Z][a-zA-Z]*(?:-[A-Z][a-zA-Z]*)*(?:App|Service|Project|Module|System|Platform|Engine|Hub|Flow|Bridge|Agent|Portal|Center))\b"
    )

    MODULE_PATTERN: re.Pattern[str] = re.compile(
        r"\b([a-z][a-z0-9_]*\.(?:api|service|controller|repository|manager|handler|config|util|model|dto|vo|dao|mapper|common|core|infra|domain|gateway|client)s?)\b"
    )

    def _extract_projects(self, text: str) -> list[str]:
        matches = self.PROJECT_PATTERN.findall(text)
        return list(dict.fromkeys(matches))

    def _extract_modules(self, text: str) -> list[str]:
        matches = self.MODULE_PATTERN.findall(text)
        return list(dict.fromkeys(matches))


entity_extractor = EntityExtractor()
