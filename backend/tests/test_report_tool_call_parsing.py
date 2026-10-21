from app.services.report_agent import ReportAgent


def parse(response):
    return ReportAgent.__new__(ReportAgent)._parse_tool_calls(response)


def test_the_standard_tag():
    response = 'Let me look.\n<tool_call>{"name": "search_posts", "parameters": {"query": "price"}}</tool_call>'

    assert parse(response) == [{"name": "search_posts", "parameters": {"query": "price"}}]


def test_a_call_closed_with_the_plural_tag():
    # DeepSeek V4 Pro, 2026-10-21: wraps the call in <tool_calls> and closes only the outer tag
    response = (
        "Now I need to understand the combinations. Let me use insight_forge.\n\n"
        "<tool_calls>\n<tool_call>\n"
        '{"name": "insight_forge", "parameters": {"query": "strongest combinations", "report_context": "summary"}}'
        "</tool_calls>"
    )

    assert parse(response) == [
        {"name": "insight_forge", "parameters": {"query": "strongest combinations", "report_context": "summary"}}
    ]


def test_an_unclosed_tag_at_the_end():
    response = '<tool_call>\n{"name": "survey_answers", "parameters": {}}'

    assert parse(response) == [{"name": "survey_answers", "parameters": {}}]


def test_several_calls():
    response = (
        '<tool_call>{"name": "search_posts", "parameters": {"query": "a"}}</tool_call>\n'
        '<tool_call>{"name": "simulation_statistics", "parameters": {}}</tool_call>'
    )

    assert [c["name"] for c in parse(response)] == ["search_posts", "simulation_statistics"]


def test_a_final_answer_has_no_calls():
    assert parse("## Summary\n\nSingapore planners lead adoption; 12 of 31 say MAYBE.") == []


def test_bare_json_still_works():
    assert parse('{"tool": "quick_search", "params": {"query": "x"}}') == [
        {"name": "quick_search", "parameters": {"query": "x"}}
    ]


def test_the_invoke_form():
    # DeepSeek V4 Pro, 2026-10-21, second attempt
    response = (
        "Let me use insight_forge.\n\n<tool_calls>\n"
        '<invoke name="insight_forge">\n'
        '<parameter name="query">Which combinations were strongest?</parameter>\n'
        '<parameter name="report_context">Executive Summary</parameter>\n'
        "</invoke>\n</tool_calls>"
    )

    assert parse(response) == [
        {"name": "insight_forge",
         "parameters": {"query": "Which combinations were strongest?", "report_context": "Executive Summary"}}
    ]


def test_invoke_parameters_that_are_json_keep_their_type():
    response = '<invoke name="search_posts"><parameter name="limit">20</parameter><parameter name="query">price</parameter></invoke>'

    assert parse(response) == [{"name": "search_posts", "parameters": {"limit": 20, "query": "price"}}]
