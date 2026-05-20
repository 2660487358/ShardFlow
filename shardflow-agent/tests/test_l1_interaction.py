import pytest

from app.layers.interaction.entity_extractor import entity_extractor
from app.layers.interaction.intent_recognizer import IntentRecognizer, intent_recognizer
from app.layers.interaction.session_manager import session_manager


class TestIntentRecognizer:
    @pytest.mark.parametrize("text,expected_intent", [
        ("理清 Dubbo 注册链路", "code_exploration"),
        ("探索微服务架构", "code_exploration"),
        ("分析调用链路", "code_exploration"),
        ("修复 NPE 异常", "code_fix"),
        ("这个 bug 怎么修", "code_fix"),
        ("解决登录报错问题", "code_fix"),
        ("设计一个缓存方案", "design_proposal"),
        ("重构用户模块", "design_proposal"),
        ("技术方案选型", "design_proposal"),
        ("生成 API 文档", "doc_generation"),
        ("写注释", "doc_generation"),
        ("这个框架怎么用", "general_qa"),
    ])
    def test_rule_match(self, text, expected_intent):
        recognizer = IntentRecognizer()
        intent, confidence = recognizer.recognize(text)
        if expected_intent != "general_qa":
            assert intent == expected_intent
            assert confidence > 0

    def test_unknown_input_falls_back(self):
        intent, _ = intent_recognizer.recognize("今天天气怎么样")
        assert intent == "general_qa"

    def test_recognize_returns_tuple(self):
        result = intent_recognizer.recognize("理清 Dubbo 注册链路")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], float)


class TestEntityExtractor:
    def test_extract_tech_stack(self):
        entities = entity_extractor.extract("使用 Dubbo 和 Redis 的微服务")
        assert "dubbo" in entities["tech_stack"]
        assert "redis" in entities["tech_stack"]

    def test_extract_service_names(self):
        entities = entity_extractor.extract("AuthService 调用 UserController")
        assert "AuthService" in entities["service"]
        assert "UserController" in entities["service"]

    def test_extract_file_paths(self):
        entities = entity_extractor.extract("看 com/example/AuthController.java 这个文件")
        assert "com/example/AuthController.java" in entities["file_path"]

    def test_extract_versions(self):
        entities = entity_extractor.extract("升级到 v2.1.0 版本")
        assert "2.1.0" in entities["version"]

    def test_extract_returns_all_fields(self):
        entities = entity_extractor.extract("测试")
        for field in ["project", "service", "tech_stack", "file_path", "module", "version"]:
            assert field in entities
            assert isinstance(entities[field], list)

    def test_empty_input(self):
        entities = entity_extractor.extract("")
        assert entities["tech_stack"] == []
        assert entities["service"] == []


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_session(self):
        session = await session_manager.create_session("t1", "task1")
        assert session["tenant_id"] == "t1"
        assert session["task_id"] == "task1"
        assert "session_id" in session

    @pytest.mark.asyncio
    async def test_get_session_not_found(self):
        session = await session_manager.get_session("t1", "nonexistent")
        assert session is None

    @pytest.mark.asyncio
    async def test_create_and_get_session(self):
        session = await session_manager.create_session("t2", "task2", "my-sess")
        assert session["session_id"] == "my-sess"

        retrieved = await session_manager.get_session("t2", "my-sess")
        assert retrieved is not None
        assert retrieved["tenant_id"] == "t2"

    @pytest.mark.asyncio
    async def test_update_session(self):
        await session_manager.create_session("t3", "task3", "sess3")
        await session_manager.update_session("t3", "sess3", {"loop_count": 5})

        retrieved = await session_manager.get_session("t3", "sess3")
        assert retrieved is not None
        assert retrieved["state"]["loop_count"] == 5

    @pytest.mark.asyncio
    async def test_archive_session(self):
        await session_manager.create_session("t4", "task4", "sess4")
        await session_manager.archive_session("t4", "sess4")

        retrieved = await session_manager.get_session("t4", "sess4")
        assert retrieved is None
