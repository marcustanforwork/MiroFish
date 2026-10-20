import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from simulation_events import group_posts_by_agent, posts_for_round, schedule_problems  # noqa: E402


EVENT_CONFIG = {
    "initial_posts": [
        {"poster_agent_id": 7, "content": "Launch post one"},
        {"poster_agent_id": 7, "content": "Launch post two"},
        {"poster_agent_id": 3, "content": "A creator's review"},
    ],
    "scheduled_posts": [
        {"round": 19, "poster_agent_id": 7, "content": "Three days left at the launch price"},
        {"round": 20, "poster_agent_id": 7, "content": "Full prices from today"},
        {"round": 20, "poster_agent_id": 3, "content": "My honest review, two months on"},
    ],
}


def test_round_zero_gives_the_initial_posts():
    assert [p["content"] for p in posts_for_round(EVENT_CONFIG, 0)] == [
        "Launch post one", "Launch post two", "A creator's review",
    ]


def test_later_rounds_give_their_scheduled_posts_in_order():
    assert [p["content"] for p in posts_for_round(EVENT_CONFIG, 20)] == [
        "Full prices from today", "My honest review, two months on",
    ]
    assert posts_for_round(EVENT_CONFIG, 5) == []


def test_invalid_entries_are_skipped():
    config = {"scheduled_posts": [
        {"round": 2, "poster_agent_id": "x", "content": "bad id"},
        {"round": 2, "poster_agent_id": 1, "content": "   "},
        {"round": "2", "poster_agent_id": 1, "content": "round as text"},
        {"round": 2, "content": "no poster"},
        "not a dict",
        {"round": 2, "poster_agent_id": 1, "content": "good"},
    ]}

    assert [p["content"] for p in posts_for_round(config, 2)] == ["round as text", "good"]


def test_missing_config_gives_no_posts():
    assert posts_for_round({}, 0) == []
    assert posts_for_round(None, 3) == []


def test_group_posts_by_agent_keeps_every_post_and_their_order():
    grouped = group_posts_by_agent(posts_for_round(EVENT_CONFIG, 0))

    assert grouped == {7: ["Launch post one", "Launch post two"], 3: ["A creator's review"]}
    assert list(grouped) == [7, 3]


def test_schedule_problems_flag_rounds_past_the_end_and_unknown_posters():
    problems = schedule_problems(EVENT_CONFIG, total_rounds=19, agent_ids={3})

    assert any("round 20" in p and "after the last round (19)" in p for p in problems)
    assert any("agent 7" in p for p in problems)


def test_schedule_problems_empty_for_a_valid_schedule():
    assert schedule_problems(EVENT_CONFIG, total_rounds=60, agent_ids={3, 7}) == []
