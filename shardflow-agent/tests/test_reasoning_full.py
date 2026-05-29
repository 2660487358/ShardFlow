import pytest

from app.layers.reasoning.decision_reasoning import (
    SubTask,
    confidence_scorer,
    plan_executor,
    task_planner,
)


class TestTaskPlannerDecompose:
    def test_decompose_research_intent_zh(self):
        subtasks = task_planner._heuristic_decompose("调研 Spring Cloud 和 Dubbo 的区别")
        assert len(subtasks) == 4
        assert subtasks[0].description == "明确调研目标和范围"
        assert subtasks[1].depends_on == ["s1"]

    def test_decompose_research_intent_en(self):
        subtasks = task_planner._heuristic_decompose("research microservice frameworks")
        assert len(subtasks) == 4

    def test_decompose_writing_intent(self):
        subtasks = task_planner._heuristic_decompose("写一份项目总结报告")
        assert len(subtasks) == 4
        assert subtasks[2].description == "撰写内容初稿"

    def test_decompose_scheduling_intent(self):
        subtasks = task_planner._heuristic_decompose("安排下周的团队会议")
        assert len(subtasks) == 3
        assert subtasks[2].description == "安排日程或发送邀请"

    def test_decompose_planning_intent(self):
        subtasks = task_planner._heuristic_decompose("规划下个季度的开发计划")
        assert len(subtasks) == 4
        assert subtasks[0].priority == 1
        assert subtasks[3].priority == 2

    def test_decompose_communication_intent(self):
        subtasks = task_planner._heuristic_decompose("发送通知给所有开发人员")
        assert len(subtasks) == 3

    def test_decompose_analyze_chain_intent(self):
        subtasks = task_planner._heuristic_decompose("分析 Dubbo 注册链路")
        assert len(subtasks) == 4
        assert subtasks[0].description == "明确调研目标和范围"

    def test_decompose_fix_intent_zh(self):
        subtasks = task_planner._heuristic_decompose("修复空指针报错")
        assert len(subtasks) == 4
        assert subtasks[2].description == "Design fix approach"

    def test_decompose_design_intent_zh(self):
        subtasks = task_planner._heuristic_decompose("设计缓存架构方案")
        assert len(subtasks) == 4
        assert "方案" in subtasks[2].description or "design" in subtasks[2].description.lower()

    def test_decompose_unknown_goal(self):
        subtasks = task_planner._heuristic_decompose("这是一段无关文本")
        assert len(subtasks) == 3
        assert "Analyze:" in subtasks[0].description

    def test_decompose_long_goal_truncated(self):
        long_goal = "a" * 200
        subtasks = task_planner._heuristic_decompose(long_goal)
        assert "a" * 60 in subtasks[0].description
        assert len(subtasks[0].description) <= 70

    def test_all_subtasks_valid_structure(self):
        goals = [
            "调研微服务框架",
            "写技术文档",
            "分析注册中心链路",
            "修复 bug",
            "设计方案",
        ]
        for goal in goals:
            subtasks = task_planner._heuristic_decompose(goal)
            ids = {s.id for s in subtasks}
            for s in subtasks:
                assert s.id.startswith("s")
                assert s.description
                assert isinstance(s.depends_on, list)
                for dep in s.depends_on:
                    assert dep in ids
                assert 1 <= s.priority <= 3


class TestTaskPlannerAsync:
    @pytest.mark.asyncio
    async def test_decompose_goal_with_context(self):
        subtasks = await task_planner.decompose_goal(
            "analyze the payment module",
            context={"user_id": "u1", "session": "s1"},
        )
        assert len(subtasks) >= 3

    @pytest.mark.asyncio
    async def test_decompose_goal_without_context(self):
        subtasks = await task_planner.decompose_goal("fix memory leak")
        assert len(subtasks) == 4


class TestTaskPlannerPrioritize:
    def test_prioritize_respects_priority_order(self):
        subtasks = [
            SubTask(id="s1", description="low", priority=3, depends_on=[]),
            SubTask(id="s2", description="high", priority=1, depends_on=[]),
            SubTask(id="s3", description="mid", priority=2, depends_on=[]),
        ]
        sorted_tasks = task_planner.prioritize(subtasks)
        assert sorted_tasks[0].priority == 1
        assert sorted_tasks[1].priority == 2
        assert sorted_tasks[2].priority == 3

    def test_prioritize_with_dependencies(self):
        subtasks = [
            SubTask(id="s1", description="base", priority=1, depends_on=[]),
            SubTask(id="s2", description="depends", priority=1, depends_on=["s1"]),
        ]
        sorted_tasks = task_planner.prioritize(subtasks)
        assert sorted_tasks[0].id == "s1"

    def test_prioritize_empty_list(self):
        assert task_planner.prioritize([]) == []


class TestTaskPlannerEffort:
    def test_estimate_effort_default_tokens(self):
        subtasks = [
            SubTask(id="s1", description="task1"),
            SubTask(id="s2", description="task2"),
        ]
        effort = task_planner.estimate_effort(subtasks)
        assert effort == {"s1": 1000, "s2": 1000}

    def test_estimate_effort_custom_tokens(self):
        subtasks = [
            SubTask(id="s1", description="task1", estimated_tokens=2000),
            SubTask(id="s2", description="task2", estimated_tokens=500),
        ]
        effort = task_planner.estimate_effort(subtasks)
        assert effort == {"s1": 2000, "s2": 500}

    def test_estimate_effort_empty(self):
        assert task_planner.estimate_effort([]) == {}


class TestPlanExecutorDAG:
    def test_build_dag_simple(self):
        subtasks = [
            SubTask(id="s1", description="base", depends_on=[]),
            SubTask(id="s2", description="step2", depends_on=["s1"]),
        ]
        dag = plan_executor.build_dag(subtasks)
        assert dag == {"s1": set(), "s2": {"s1"}}

    def test_build_dag_multiple_deps(self):
        subtasks = [
            SubTask(id="s1", description="base1", depends_on=[]),
            SubTask(id="s2", description="base2", depends_on=[]),
            SubTask(id="s3", description="merge", depends_on=["s1", "s2"]),
        ]
        dag = plan_executor.build_dag(subtasks)
        assert dag["s3"] == {"s1", "s2"}

    def test_build_dag_empty(self):
        assert plan_executor.build_dag([]) == {}


class TestPlanExecutorNextTasks:
    def test_get_next_tasks_initial(self):
        subtasks = [
            SubTask(id="s1", description="base", depends_on=[]),
            SubTask(id="s2", description="step2", depends_on=["s1"]),
        ]
        dag = plan_executor.build_dag(subtasks)
        ready = plan_executor.get_next_tasks(dag, set())
        assert ready == ["s1"]

    def test_get_next_tasks_after_first(self):
        subtasks = [
            SubTask(id="s1", description="base", depends_on=[]),
            SubTask(id="s2", description="step2", depends_on=["s1"]),
        ]
        dag = plan_executor.build_dag(subtasks)
        ready = plan_executor.get_next_tasks(dag, {"s1"})
        assert ready == ["s2"]

    def test_get_next_tasks_multiple_ready(self):
        subtasks = [
            SubTask(id="s1", description="base1", depends_on=[]),
            SubTask(id="s2", description="base2", depends_on=[]),
            SubTask(id="s3", description="merge", depends_on=["s1", "s2"]),
        ]
        dag = plan_executor.build_dag(subtasks)
        ready = plan_executor.get_next_tasks(dag, set())
        assert set(ready) == {"s1", "s2"}

    def test_get_next_tasks_all_completed(self):
        subtasks = [
            SubTask(id="s1", description="task", depends_on=[]),
        ]
        dag = plan_executor.build_dag(subtasks)
        ready = plan_executor.get_next_tasks(dag, {"s1"})
        assert ready == []

    def test_get_next_tasks_empty_dag(self):
        assert plan_executor.get_next_tasks({}, set()) == []


class TestPlanExecutorCompletion:
    def test_check_completion_empty_dag(self):
        assert plan_executor.check_completion({}, set()) is True

    def test_check_completion_none_done(self):
        dag = {"s1": set(), "s2": set()}
        assert plan_executor.check_completion(dag, set()) is False

    def test_check_completion_partial(self):
        dag = {"s1": set(), "s2": set(), "s3": set()}
        assert plan_executor.check_completion(dag, {"s1"}) is False

    def test_check_completion_all_done(self):
        dag = {"s1": set(), "s2": set(), "s3": set()}
        assert plan_executor.check_completion(dag, {"s1", "s2", "s3"}) is True


class TestConfidenceScorerCompletion:
    def test_score_zero_progress(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 5,
            "subtasks_done": 0,
            "pending": ["a", "b", "c", "d", "e"],
            "context_usage_ratio": 0.0,
        })
        assert 0.0 <= score <= 0.5

    def test_score_half_progress(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 4,
            "subtasks_done": 2,
            "pending": ["c", "d"],
            "context_usage_ratio": 0.5,
        })
        assert 0.3 <= score <= 0.7

    def test_score_full_progress(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 3,
            "subtasks_done": 3,
            "pending": [],
            "context_usage_ratio": 0.2,
        })
        assert score > 0.7

    def test_score_with_high_usage(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 3,
            "subtasks_done": 2,
            "pending": ["c"],
            "context_usage_ratio": 0.9,
        })
        assert score < 0.6

    def test_score_missing_fields_defaults(self):
        score = confidence_scorer.score_completion({})
        assert 0.0 <= score <= 1.0


class TestConfidenceScorerFact:
    def test_score_fact_no_evidence(self):
        score = confidence_scorer.score_individual_fact({
            "evidence": [],
            "confidence": 0.5,
        })
        assert 0.0 <= score <= 0.5

    def test_score_fact_partial_evidence(self):
        score = confidence_scorer.score_individual_fact({
            "evidence": ["source1"],
            "confidence": 0.7,
        })
        assert 0.3 <= score <= 0.7

    def test_score_fact_full_evidence(self):
        score = confidence_scorer.score_individual_fact({
            "evidence": ["source1", "source2", "source3"],
            "confidence": 0.9,
        })
        assert score > 0.7

    def test_score_fact_missing_fields(self):
        score = confidence_scorer.score_individual_fact({})
        assert 0.0 <= score <= 1.0


class TestConfidenceScorerRecommendContinue:
    def test_recommend_early_stage(self):
        assert confidence_scorer.recommend_continue({
            "subtasks_total": 5,
            "subtasks_done": 1,
            "pending": ["b", "c", "d", "e"],
            "context_usage_ratio": 0.3,
        }) is True

    def test_recommend_mid_stage(self):
        state = {
            "subtasks_total": 4,
            "subtasks_done": 2,
            "pending": ["c", "d"],
            "context_usage_ratio": 0.5,
        }
        score = confidence_scorer.score_completion(state)
        if score < 0.7:
            assert confidence_scorer.recommend_continue(state) is True
        else:
            assert confidence_scorer.recommend_continue(state) is False

    def test_recommend_near_complete(self):
        assert confidence_scorer.recommend_continue({
            "subtasks_total": 3,
            "subtasks_done": 3,
            "pending": [],
            "context_usage_ratio": 0.1,
        }) is False

    def test_recommend_high_usage(self):
        assert confidence_scorer.recommend_continue({
            "subtasks_total": 5,
            "subtasks_done": 4,
            "pending": ["e"],
            "context_usage_ratio": 0.95,
        }) is True
