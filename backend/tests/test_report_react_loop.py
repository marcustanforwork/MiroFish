from unittest.mock import MagicMock

from app.services.report_agent import ReportAgent, ReportOutline, ReportSection
from tests.test_report_simulation_tools import StubActivityStore

STATS_CALL = '<tool_call>{"name": "simulation_statistics", "parameters": {}}</tool_call>'


def agent_answering(*responses):
    llm = MagicMock()
    llm.chat.side_effect = list(responses)
    return ReportAgent(
        graph_id="g", simulation_id="s", simulation_requirement="r",
        llm_client=llm, zep_tools=MagicMock(), activity_store=StubActivityStore(),
        interviews_available=False,
    ), llm


def write_section(agent):
    section = ReportSection(title="Summary")
    return agent._generate_section_react(section, ReportOutline(title="T", summary="S", sections=[section]), [])


def test_a_tool_call_in_a_format_nobody_reads_is_never_the_chapter():
    agent, llm = agent_answering(
        STATS_CALL, STATS_CALL, STATS_CALL,
        '<tool_calls><call tool="insight_forge">{"query": "x"}</call></tool_calls>',
        "Final Answer: Singapore planners lead.",
    )

    assert write_section(agent) == "Singapore planners lead."
    assert "<tool_call>" in llm.chat.call_args.kwargs["messages"][-1]["content"]


def test_plain_text_after_enough_tool_calls_is_still_the_chapter():
    agent, _ = agent_answering(STATS_CALL, STATS_CALL, STATS_CALL, "Singapore planners lead.")

    assert write_section(agent) == "Singapore planners lead."
