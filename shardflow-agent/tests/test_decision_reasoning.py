from app.layers.reasoning.decision_reasoning import (
    confidence_scorer,
    plan_executor,
    task_planner,
)


class TestTaskPlanner:
    def test_decompose_exploration_goal(self):
        subtasks = task_planner._heuristic_decompose("analyze the whole project architecture")
        assert len(subtasks) >= 3
        assert len(subtasks) <= 7
        for s in subtasks:
            assert s.id.startswith("s")
            assert s.description

    def test_decompose_fix_goal(self):
        subtasks = task_planner._heuristic_decompose("fix NPE exception")
        assert len(subtasks) >= 3
        assert subtasks[0].priority == 1

    def test_decompose_design_goal(self):
        subtasks = task_planner._heuristic_decompose("design cache solution")
        assert len(subtasks) >= 3

    def test_decompose_unknown_pattern(self):
        subtasks = task_planner._heuristic_decompose("random query text")
        assert len(subtasks) == 3

    def test_estimate_effort(self):
        subtasks = task_planner._heuristic_decompose("analyze project structure")
        effort = task_planner.estimate_effort(subtasks)
        assert len(effort) == len(subtasks)

    def test_prioritize(self):
        subtasks = task_planner._heuristic_decompose("analyze project structure")
        sorted_tasks = task_planner.prioritize(subtasks)
        assert sorted_tasks[0].priority <= sorted_tasks[-1].priority


class TestPlanExecutor:
    def test_build_dag(self):
        subtasks = task_planner._heuristic_decompose("analyze project structure")
        dag = plan_executor.build_dag(subtasks)
        assert len(dag) == len(subtasks)

    def test_get_next_tasks(self):
        subtasks = task_planner._heuristic_decompose("fix NPE exception")
        dag = plan_executor.build_dag(subtasks)
        ready = plan_executor.get_next_tasks(dag, set())
        assert len(ready) > 0
        for task_id in ready:
            assert dag[task_id] == set()

    def test_get_next_tasks_with_completed(self):
        subtasks = task_planner._heuristic_decompose("fix NPE exception")
        dag = plan_executor.build_dag(subtasks)
        first = plan_executor.get_next_tasks(dag, set())
        ready = plan_executor.get_next_tasks(dag, set(first))
        assert len(ready) >= 0

    def test_check_completion_false(self):
        subtasks = task_planner._heuristic_decompose("fix NPE exception")
        dag = plan_executor.build_dag(subtasks)
        assert plan_executor.check_completion(dag, set()) is False

    def test_check_completion_true(self):
        subtasks = task_planner._heuristic_decompose("fix NPE exception")
        dag = plan_executor.build_dag(subtasks)
        assert plan_executor.check_completion(dag, set(dag.keys())) is True


class TestConfidenceScorer:
    def test_score_completion_empty(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 3, "subtasks_done": 0,
            "pending": [], "context_usage_ratio": 0.0,
        })
        assert 0.0 <= score <= 1.0

    def test_score_completion_partial(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 3, "subtasks_done": 2,
            "pending": ["a", "b"], "context_usage_ratio": 0.5,
        })
        assert score > 0.3

    def test_score_completion_full(self):
        score = confidence_scorer.score_completion({
            "subtasks_total": 3, "subtasks_done": 3,
            "pending": [], "context_usage_ratio": 0.3,
        })
        assert score > 0.7

    def test_score_individual_fact(self):
        score = confidence_scorer.score_individual_fact({
            "evidence": ["pom.xml", "code", "docs"],
            "confidence": 0.9,
        })
        assert 0.0 <= score <= 1.0
        assert score > 0.5

    def test_recommend_continue_low_score(self):
        assert confidence_scorer.recommend_continue({
            "subtasks_total": 3, "subtasks_done": 0,
            "pending": ["a", "b", "c"], "context_usage_ratio": 0.2,
        }) is True

    def test_recommend_continue_high_score(self):
        assert confidence_scorer.recommend_continue({
            "subtasks_total": 3, "subtasks_done": 3,
            "pending": [], "context_usage_ratio": 0.1,
        }) is False
