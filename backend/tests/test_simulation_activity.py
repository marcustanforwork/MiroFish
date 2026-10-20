import json
import sqlite3

import pytest

from app.services.simulation_activity import (
    SimulationActivityStore,
    country_to_region,
    format_search_results,
    format_statistics,
    format_survey_answers,
)


@pytest.mark.parametrize(
    ("country", "region"),
    [
        ("新加坡", "Southeast Asia"),
        ("Singapore (新加坡)", "Southeast Asia"),
        ("印度尼西亚", "Southeast Asia"),
        ("日本", "Japan and Korea"),
        ("South Korea", "Japan and Korea"),
        ("中国", "Greater China"),
        ("印度", "India and South Asia"),
        ("United States", "North America"),
        ("美国", "North America"),
        ("英国", "UK and Europe"),
        ("阿联酋", "Middle East"),
        ("巴西", "Latin America"),
        ("Kenya", "Africa"),
        ("Australia", "Australia and New Zealand"),
        ("Atlantis", "Unknown"),
        (None, "Unknown"),
        ("", "Unknown"),
    ],
)
def test_country_to_region(country, region):
    assert country_to_region(country) == region


def test_agents_carry_segment_and_region(sim_dir):
    agents = SimulationActivityStore(str(sim_dir)).agents

    assert agents[1].entity_type == "EventPlanner"
    assert agents[1].region == "Japan and Korea"
    assert agents[3].region == "North America"


def test_records_skip_round_events_and_resolve_comment_targets(sim_dir):
    records = SimulationActivityStore(str(sim_dir)).records()

    assert len(records) == 6
    comment = next(r for r in records if r.action_type == "CREATE_COMMENT")
    assert comment.round_num == 1
    assert comment.target_author == "Acme"
    assert comment.target_text == "We are one founder in Singapore. What would stop you?"


def test_search_ranks_written_content_by_query_terms(sim_dir):
    results = SimulationActivityStore(str(sim_dir)).search("WhatsApp free family")

    assert [r.action_type for r in results] == ["QUOTE_POST"]
    assert results[0].text == "WhatsApp is free and good enough for my family."


def test_search_ignores_likes_and_filters_by_region(sim_dir):
    store = SimulationActivityStore(str(sim_dir))

    assert all(r.action_type != "LIKE_POST" for r in store.search("half"))
    japan = store.search("venues invoices download", region="Japan and Korea")
    assert [r.agent_name for r in japan] == ["Tokyo planner"]


def test_search_with_no_match_returns_empty(sim_dir):
    assert SimulationActivityStore(str(sim_dir)).search("cryptocurrency") == []


def test_statistics_summarise_activity(sim_dir):
    stats = SimulationActivityStore(str(sim_dir)).statistics()

    assert stats["total_actions"] == 6
    assert stats["by_platform"] == {"twitter": 4, "reddit": 2}
    assert stats["idle_actions"] == 1
    assert stats["total_agents"] == 4
    assert stats["active_agents"] == 3
    assert stats["rounds"][1] == {"round": 1, "twitter": 2, "reddit": 1}
    assert stats["by_segment"]["EventVendor"] == {"agents": 1, "active_agents": 0, "actions": 0, "written": 0}
    assert stats["by_region"]["Southeast Asia"]["written"] == 3


def test_statistics_rank_top_posts_by_engagement(sim_dir):
    top = SimulationActivityStore(str(sim_dir)).statistics()["top_posts"]

    assert top[0]["author"] == "Acme"
    assert top[0]["platform"] == "twitter"
    assert (top[0]["likes"], top[0]["shares"], top[0]["comments"]) == (5, 2, 0)
    reddit_first = next(p for p in top if p["platform"] == "reddit")
    assert reddit_first["comments"] == 1


def test_survey_answers_keep_latest_per_agent_and_platform(sim_dir):
    answers = SimulationActivityStore(str(sim_dir)).survey_answers()

    assert len(answers) == 2
    guest = next(a for a in answers if a.agent_id == 2)
    assert guest.response.startswith("1. NO")
    assert guest.region == "Southeast Asia"


def test_survey_answers_filter_by_query(sim_dir):
    answers = SimulationActivityStore(str(sim_dir)).survey_answers("JPY partner")

    assert [a.agent_name for a in answers] == ["Tokyo planner"]


def test_missing_files_give_empty_results(tmp_path):
    store = SimulationActivityStore(str(tmp_path))

    assert store.agents == {}
    assert store.records() == []
    assert store.search("anything") == []
    assert store.survey_answers() == []
    assert store.statistics()["total_actions"] == 0


def test_formatters_render_readable_text(sim_dir):
    store = SimulationActivityStore(str(sim_dir))

    search_text = format_search_results(store.search("JPY invoices"), store.agents)
    assert "Tokyo planner" in search_text and "EventPlanner" in search_text and "Japan and Korea" in search_text
    assert "replying to Acme" in search_text

    stats_text = format_statistics(store.statistics())
    assert "Total actions: 6" in stats_text and "Southeast Asia" in stats_text

    survey_text = format_survey_answers(store.survey_answers())
    assert "Wedding guest" in survey_text and "1. NO" in survey_text

    assert "No matching" in format_search_results([], store.agents)
    assert "No survey answers" in format_survey_answers([])


@pytest.mark.parametrize(
    ("country", "region"),
    [
        ("Romania", "UK and Europe"),
        ("Indiana, USA", "North America"),
        ("Oman", "Middle East"),
        ("India", "India and South Asia"),
        ("Mumbai, India", "India and South Asia"),
    ],
)
def test_country_to_region_matches_whole_words(country, region):
    assert country_to_region(country) == region


def test_malformed_action_lines_are_skipped(sim_dir):
    with open(sim_dir / "twitter" / "actions.jsonl", "a", encoding="utf-8") as f:
        f.write('5\n{"round": 2, "agent_id": null, "action_type": "CREATE_POST", "action_args": {"content": "x"}}\nnot json\n')

    records = SimulationActivityStore(str(sim_dir)).records()

    assert len(records) == 6


def test_survey_answers_ignore_prompt_only_and_later_ad_hoc_interviews(sim_dir):
    con = sqlite3.connect(sim_dir / "reddit_simulation.db")
    con.executemany(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, 'interview', ?)",
        [
            (1, "2026-10-20 00:30:00", json.dumps({"prompt": "only a prompt"})),
            (1, "2026-10-20 00:40:00", json.dumps({"prompt": "What do you think of the venue?", "response": "It was fine."})),
        ],
    )
    con.commit()
    con.close()

    answers = SimulationActivityStore(str(sim_dir)).survey_answers(prompt_contains="survey")

    planner = next(a for a in answers if a.agent_id == 1)
    assert planner.response.startswith("1. MAYBE")


def test_statistics_totals_reconcile_with_breakdowns(sim_dir):
    with open(sim_dir / "reddit" / "actions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"round": 2, "agent_id": 99, "agent_name": "ghost", "action_type": "LIKE_POST", "action_args": {}}) + "\n")

    stats = SimulationActivityStore(str(sim_dir)).statistics()

    assert stats["total_actions"] - stats["idle_actions"] == sum(g["actions"] for g in stats["by_segment"].values())
    assert sum(stats["by_platform"].values()) == stats["total_actions"]
