from unittest.mock import MagicMock

import pytest

from app.services.report_agent import ReportAgent
from app.services.simulation_activity import ActivityRecord, AgentInfo, SurveyAnswer


class StubActivityStore:
    agents = {
        1: AgentInfo(agent_id=1, name="Tokyo planner", entity_type="EventPlanner", country="日本", region="Japan and Korea"),
    }

    def __init__(self):
        self.search_calls = []

    def search(self, query, limit=10, platform=None, segment=None, region=None):
        self.search_calls.append(
            {"query": query, "limit": limit, "platform": platform, "segment": segment, "region": region}
        )
        return [
            ActivityRecord(
                platform="reddit", round_num=3, agent_id=1, agent_name="Tokyo planner",
                action_type="CREATE_COMMENT", text="Japanese venues need JPY invoices first.",
                target_author="Acme", target_text="What would stop you?",
            )
        ]

    def statistics(self, top_n=10):
        return {
            "total_actions": 12, "idle_actions": 2, "by_platform": {"twitter": 5, "reddit": 7},
            "by_action_type": {"CREATE_COMMENT": 4}, "total_agents": 3, "active_agents": 2,
            "rounds": [{"round": 0, "twitter": 1, "reddit": 2}],
            "by_segment": {"EventPlanner": {"agents": 1, "active_agents": 1, "actions": 4, "written": 4}},
            "by_region": {"Japan and Korea": {"agents": 1, "active_agents": 1, "actions": 4, "written": 4}},
            "top_agents": [], "top_posts": [],
        }

    def survey_answers(self, query="", limit=200):
        return [
            SurveyAnswer(platform="reddit", agent_id=1, agent_name="Tokyo planner", entity_type="EventPlanner",
                         region="Japan and Korea", response="1. MAYBE - only with a local partner.", created_at="")
        ]


def _agent(interviews_available=False, store=None):
    zep_tools = MagicMock()
    zep_tools.get_simulation_context.return_value = {
        "graph_statistics": {"total_nodes": 1, "total_edges": 0, "entity_types": {}},
        "total_entities": 1,
        "related_facts": [],
    }
    return ReportAgent(
        graph_id="graph_1",
        simulation_id="sim_1",
        simulation_requirement="Simulate the launch.",
        llm_client=MagicMock(),
        zep_tools=zep_tools,
        activity_store=store or StubActivityStore(),
        interviews_available=interviews_available,
    )


def test_simulation_tools_are_offered():
    tools = _agent().tools

    assert {"search_posts", "simulation_statistics", "survey_answers"} <= set(tools)


def test_interview_tool_hidden_when_environment_is_closed():
    assert "interview_agents" not in _agent(interviews_available=False).tools
    assert "interview_agents" in _agent(interviews_available=True).tools


def test_search_posts_passes_filters_and_returns_exact_text():
    store = StubActivityStore()
    result = _agent(store=store)._execute_tool(
        "search_posts", {"query": "JPY invoices", "limit": "3", "region": "Japan and Korea"}
    )

    assert store.search_calls == [
        {"query": "JPY invoices", "limit": 3, "platform": None, "segment": None, "region": "Japan and Korea"}
    ]
    assert "Japanese venues need JPY invoices first." in result
    assert "replying to Acme" in result


def test_simulation_statistics_tool_returns_counts():
    result = _agent()._execute_tool("simulation_statistics", {})

    assert "Total actions: 12" in result
    assert "Japan and Korea" in result


def test_survey_answers_tool_returns_answers():
    result = _agent()._execute_tool("survey_answers", {"query": "partner"})

    assert "Tokyo planner" in result and "local partner" in result


def test_new_tools_are_valid_tool_call_names():
    assert {"search_posts", "simulation_statistics", "survey_answers"} <= ReportAgent.VALID_TOOL_NAMES


@pytest.mark.parametrize("interviews_available", [False, True])
def test_tool_suggestions_list_only_offered_tools(interviews_available):
    suggestions = _agent(interviews_available=interviews_available)._get_tool_suggestions()

    assert "search_posts" in suggestions
    assert ("interview_agents" in suggestions) is interviews_available


def test_outline_planning_sees_simulation_statistics():
    agent = _agent()
    agent.llm.chat_json.return_value = {
        "title": "T", "summary": "S", "sections": [{"title": "A", "description": "a"}, {"title": "B", "description": "b"}],
    }

    agent.plan_outline()

    user_prompt = agent.llm.chat_json.call_args.kwargs["messages"][1]["content"]
    assert "Total actions: 12" in user_prompt


def test_hidden_interview_tool_is_rejected_at_execution():
    result = _agent(interviews_available=False)._execute_tool("interview_agents", {"interview_topic": "x"})

    offered = result.split(":", 2)[-1]
    assert result.startswith("未知工具")
    assert "search_posts" in offered and "interview_agents" not in offered


def test_env_check_failure_hides_interviews(monkeypatch):
    from app.services import simulation_runner

    def boom(_simulation_id):
        raise OSError("read-only")

    monkeypatch.setattr(simulation_runner.SimulationRunner, "check_env_alive", staticmethod(boom))
    zep_tools = MagicMock()
    agent = ReportAgent(graph_id="g", simulation_id="s", simulation_requirement="r",
                        llm_client=MagicMock(), zep_tools=zep_tools, activity_store=StubActivityStore())

    assert "interview_agents" not in agent.tools


@pytest.mark.parametrize("limit", [None, 2.0, "abc"])
def test_search_posts_tolerates_bad_limits(limit):
    store = StubActivityStore()
    _agent(store=store)._execute_tool("search_posts", {"query": "JPY", "limit": limit})

    assert store.search_calls[0]["limit"] in (2, 10)
