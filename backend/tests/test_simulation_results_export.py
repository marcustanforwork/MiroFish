import json

import pytest

from app.services.simulation_activity import SimulationActivityStore, parse_intent, parse_role
from app.services.simulation_results_export import export_results


@pytest.mark.parametrize(
    ("response", "intent"),
    [
        ("1. **MAYBE** — it genuinely worked, but consent worries me.", "MAYBE"),
        ("1. YES — my villas already own the screens.", "YES"),
        ("1. NO. WhatsApp is enough.", "NO"),
        ("1. Yes, because guests never install anything.", "YES"),
        ("Answer: 1. maybe - depends on price\n2. S$50", "MAYBE"),
        ("I would not use it. 2. Prices...", ""),
        ("", ""),
    ],
)
def test_parse_intent(response, intent):
    assert parse_intent(response) == intent


@pytest.fixture
def report_dir(tmp_path):
    folder = tmp_path / "report"
    folder.mkdir()
    (folder / "outline.json").write_text(json.dumps({
        "title": "Who says yes",
        "summary": "Trial forms in Southeast Asia.",
        "sections": [{"title": "The verdict"}, {"title": "Objections"}],
    }), encoding="utf-8")
    (folder / "section_01.md").write_text(
        "## The verdict\n\n**The shape**\n\n> \"a quote\"\n\nTrial forms where the discount is legible.\n\nMore text.",
        encoding="utf-8",
    )
    (folder / "section_02.md").write_text("WhatsApp is free travels fastest.", encoding="utf-8")
    return folder


def _read(out, name):
    return json.loads((out / name).read_text(encoding="utf-8"))


def test_export_writes_every_dataset(sim_dir, report_dir, tmp_path):
    (sim_dir / "simulation.log").write_text("[通用LLM][SIM] model=deepseek/flash@preset/x, base_url=...\n", encoding="utf-8")
    out = tmp_path / "out"

    written = export_results(SimulationActivityStore(str(sim_dir)), str(out), report_dir=str(report_dir), label="Pilot")

    assert sorted(written) == sorted([
        "kpis.json", "rounds.json", "segments.json", "regions.json", "action_types.json",
        "top_posts.json", "top_agents.json", "survey.json", "report_sections.json",
    ])
    kpis = _read(out, "kpis.json")
    assert kpis == [{
        "label": "Pilot", "agent_model": "deepseek/flash@preset/x", "rounds": 2,
        "total_agents": 4, "active_agents": 3, "total_actions": 6, "idle_actions": 1, "idle_share": 1 / 6,
        "written": 4, "twitter_actions": 4, "reddit_actions": 2, "survey_answers": 2,
    }]
    assert _read(out, "rounds.json")[1] == {"round": 1, "twitter": 2, "reddit": 1}
    assert {"segment": "EventVendor", "agents": 1, "active_agents": 0, "actions": 0, "written": 0} in _read(out, "segments.json")
    assert _read(out, "top_posts.json")[0]["rank"] == 1
    assert _read(out, "action_types.json")[0] == {"action_type": "CREATE_POST", "count": 2}

    survey = _read(out, "survey.json")
    assert {(s["agent"], s["intent"]) for s in survey} == {("Wedding guest", "NO"), ("Tokyo planner", "MAYBE")}

    sections = _read(out, "report_sections.json")
    assert sections[0] == {"order": 0, "title": "Who says yes", "lead": "Trial forms in Southeast Asia."}
    assert sections[1] == {"order": 1, "title": "The verdict", "lead": "Trial forms where the discount is legible."}
    assert sections[2]["lead"] == "WhatsApp is free travels fastest."


def test_export_without_report_or_log(sim_dir, tmp_path):
    out = tmp_path / "out"

    written = export_results(SimulationActivityStore(str(sim_dir)), str(out))

    assert "report_sections.json" not in written
    assert _read(out, "kpis.json")[0]["agent_model"] == ""


@pytest.mark.parametrize(
    ("response", "intent"),
    [
        ("**1. No** — not for us.", "NO"),
        ("1) Yes, we would.", "YES"),
        ("Q1: MAYBE — depends.", "MAYBE"),
        ("Some preamble about Answer 1. Yes inside a sentence", ""),
    ],
)
def test_parse_intent_more_formats(response, intent):
    assert parse_intent(response) == intent


def test_export_can_keep_only_the_survey_prompt(sim_dir, tmp_path):
    out = tmp_path / "out"

    export_results(SimulationActivityStore(str(sim_dir)), str(out), survey_prompt_contains="no such prompt")

    assert _read(out, "survey.json") == []
    assert _read(out, "kpis.json")[0]["survey_answers"] == 0


@pytest.mark.parametrize(
    ("response", "role"),
    [
        ("0. HOST — our wedding is in May.\n1. MAYBE — price.", "HOST"),
        ("**0. Channel** — I'm a planner.\n1. YES", "CHANNEL"),
        ("0) COMPETITOR\n1. n/a", "COMPETITOR"),
        ("0. NEITHER.\n1. n/a", "NEITHER"),
        ("1. MAYBE — the main run had no question 0.", ""),
        ("0. I host parties, sometimes.", ""),
    ],
)
def test_parse_role(response, role):
    assert parse_role(response) == role
