"""
Posts placed into a simulation by the operator rather than written by agents.

event_config.initial_posts are published in round 0, before any agent acts.
event_config.scheduled_posts are published at the start of the round they name,
so a long run can carry dated news (an offer ending, a price change):
    {"round": 20, "poster_agent_id": 59, "content": "Full prices from today."}

Kept free of OASIS imports so the rules can be tested on their own.
"""

from typing import Any, Dict, Iterable, List, Optional


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _valid_post(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    agent_id = _as_int(entry.get("poster_agent_id"))
    content = entry.get("content")
    if agent_id is None or not isinstance(content, str) or not content.strip():
        return None
    return {**entry, "poster_agent_id": agent_id, "content": content}


def posts_for_round(event_config: Optional[Dict[str, Any]], round_num: int) -> List[Dict[str, Any]]:
    """The posts to publish in this round: the initial posts in round 0, else that round's scheduled posts."""
    config = event_config or {}
    if round_num == 0:
        entries = config.get("initial_posts") or []
    else:
        entries = [e for e in (config.get("scheduled_posts") or [])
                   if isinstance(e, dict) and _as_int(e.get("round")) == round_num]
    return [post for post in map(_valid_post, entries) if post]


def group_posts_by_agent(posts: Iterable[Dict[str, Any]]) -> Dict[int, List[str]]:
    """Each poster's posts in order, so an agent with several posts publishes all of them."""
    grouped: Dict[int, List[str]] = {}
    for post in posts:
        grouped.setdefault(post["poster_agent_id"], []).append(post["content"])
    return grouped


def schedule_problems(
    event_config: Optional[Dict[str, Any]],
    total_rounds: int,
    agent_ids: Iterable[int],
) -> List[str]:
    """Scheduled posts that would never be published: past the last round, or by an unknown agent."""
    known = set(agent_ids)
    problems = []
    for entry in (event_config or {}).get("scheduled_posts") or []:
        post = _valid_post(entry)
        round_num = _as_int(entry.get("round")) if isinstance(entry, dict) else None
        if post is None or round_num is None or round_num < 1:
            problems.append(f"invalid scheduled post: {str(entry)[:80]}")
            continue
        if round_num > total_rounds:
            problems.append(f"scheduled post for round {round_num} is after the last round ({total_rounds})")
        if post["poster_agent_id"] not in known:
            problems.append(f"scheduled post for round {round_num} names unknown agent {post['poster_agent_id']}")
    return problems
