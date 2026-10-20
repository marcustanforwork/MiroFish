"""Shared fixtures: a small simulation folder shaped like a real MiroFish run."""

import json
import sqlite3

import pytest


AGENTS = [
    {"agent_id": 0, "entity_name": "Acme", "entity_type": "Organization"},
    {"agent_id": 1, "entity_name": "Tokyo planner", "entity_type": "EventPlanner"},
    {"agent_id": 2, "entity_name": "Wedding guest", "entity_type": "Person"},
    {"agent_id": 3, "entity_name": "Quiet vendor", "entity_type": "EventVendor"},
]
PROFILES = [
    {"user_id": 0, "name": "Acme", "country": "Singapore (新加坡)"},
    {"user_id": 1, "name": "Tokyo planner", "country": "日本"},
    {"user_id": 2, "name": "Wedding guest", "country": "新加坡"},
    {"user_id": 3, "name": "Quiet vendor", "country": "United States"},
]

TWITTER_ACTIONS = [
    {"event_type": "simulation_start", "platform": "twitter", "total_rounds": 2},
    {"round": 0, "event_type": "round_start"},
    {"round": 0, "agent_id": 0, "agent_name": "Acme", "action_type": "CREATE_POST",
     "action_args": {"content": "Half price this month. No app, just a QR code."}},
    {"round": 1, "agent_id": 2, "agent_name": "Wedding guest", "action_type": "QUOTE_POST",
     "action_args": {"original_author_name": "Acme",
                     "original_content": "Half price this month. No app, just a QR code.",
                     "quote_content": "WhatsApp is free and good enough for my family."}},
    {"round": 1, "agent_id": 1, "agent_name": "Tokyo planner", "action_type": "LIKE_POST",
     "action_args": {"post_author_name": "Acme", "post_content": "Half price this month."}},
    {"round": 2, "agent_id": 3, "agent_name": "Quiet vendor", "action_type": "DO_NOTHING", "action_args": {}},
    {"round": 2, "event_type": "round_end", "actions_count": 1},
]
REDDIT_ACTIONS = [
    {"round": 1, "agent_id": 1, "agent_name": "Tokyo planner", "action_type": "CREATE_COMMENT",
     "action_args": {"comment_id": 1, "content": "Japanese venues need JPY invoices and Japanese signage first."}},
    {"round": 2, "agent_id": 2, "agent_name": "Wedding guest", "action_type": "CREATE_POST",
     "action_args": {"content": "Guests cannot download photos? That is a dealbreaker for my aunties."}},
]


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def _create_db(path, posts, comments=(), interviews=()):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE user (user_id INTEGER PRIMARY KEY, agent_id INTEGER, user_name TEXT, name TEXT);
        CREATE TABLE post (post_id INTEGER PRIMARY KEY, user_id INTEGER, original_post_id INTEGER,
                           content TEXT DEFAULT '', quote_content TEXT, num_likes INTEGER DEFAULT 0,
                           num_shares INTEGER DEFAULT 0);
        CREATE TABLE comment (comment_id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER, content TEXT);
        CREATE TABLE trace (user_id INTEGER, created_at DATETIME, action TEXT, info TEXT);
        """
    )
    con.executemany(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        [(a["agent_id"], a["agent_id"], f"user_{a['agent_id']}", a["entity_name"]) for a in AGENTS],
    )
    con.executemany(
        "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content, num_likes, num_shares)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        posts,
    )
    con.executemany("INSERT INTO comment (comment_id, post_id, user_id, content) VALUES (?, ?, ?, ?)", comments)
    con.executemany(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, 'interview', ?)",
        [(uid, created, json.dumps({"prompt": "survey", "response": resp})) for uid, created, resp in interviews],
    )
    con.commit()
    con.close()


@pytest.fixture
def sim_dir(tmp_path):
    (tmp_path / "simulation_config.json").write_text(
        json.dumps({"agent_configs": AGENTS}), encoding="utf-8"
    )
    (tmp_path / "reddit_profiles.json").write_text(json.dumps(PROFILES, ensure_ascii=False), encoding="utf-8")
    _write_jsonl(tmp_path / "twitter" / "actions.jsonl", TWITTER_ACTIONS)
    _write_jsonl(tmp_path / "reddit" / "actions.jsonl", REDDIT_ACTIONS)
    _create_db(
        tmp_path / "twitter_simulation.db",
        posts=[
            (1, 0, None, "Half price this month. No app, just a QR code.", None, 5, 2),
            (2, 2, 1, "", "WhatsApp is free and good enough for my family.", 1, 0),
        ],
        interviews=[
            (2, "2026-10-20 00:10:00", "1. MAYBE - the QR flow is great but guests cannot download."),
            (2, "2026-10-20 00:20:00", "1. NO - WhatsApp is free and my family already uses it."),
        ],
    )
    _create_db(
        tmp_path / "reddit_simulation.db",
        posts=[
            (1, 0, None, "We are one founder in Singapore. What would stop you?", None, 3, 0),
            (2, 2, None, "Guests cannot download photos? That is a dealbreaker for my aunties.", None, 0, 0),
        ],
        comments=[(1, 1, 1, "Japanese venues need JPY invoices and Japanese signage first.")],
        interviews=[(1, "2026-10-20 00:10:00", "1. MAYBE - only with a local partner and JPY invoicing.")],
    )
    return tmp_path
