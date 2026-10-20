"""
Read a finished simulation straight from its own files.

The runner already records everything the agents did: each platform's
actions.jsonl (round, agent, action, text) and its SQLite database (posts,
comments, likes, shares, interview answers). This module turns those files
into searchable records and statistics for the ReportAgent and for the
results dashboard, so a report does not depend on Zep ingesting the run.
"""

import json
import os
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger('mirofish.simulation_activity')

PLATFORMS = ("twitter", "reddit")
IDLE_ACTION = "DO_NOTHING"
WRITTEN_ACTIONS = frozenset({"CREATE_POST", "QUOTE_POST", "CREATE_COMMENT"})
UNKNOWN_REGION = "Unknown"

# Profiles store the country as the LLM wrote it: often Chinese, sometimes
# English, sometimes both ("Singapore (新加坡)").
_REGION_ALIASES: Dict[str, Tuple[str, ...]] = {
    "Southeast Asia": (
        "singapore", "malaysia", "indonesia", "thailand", "philippines", "vietnam", "viet nam",
        "cambodia", "myanmar", "brunei", "laos",
        "新加坡", "马来西亚", "印度尼西亚", "印尼", "泰国", "菲律宾", "越南", "柬埔寨", "缅甸", "文莱", "老挝",
    ),
    "Japan and Korea": ("japan", "korea", "south korea", "日本", "韩国", "南韩"),
    "Greater China": ("china", "hong kong", "taiwan", "macau", "macao", "中国", "香港", "台湾", "澳门"),
    "India and South Asia": (
        "india", "pakistan", "bangladesh", "sri lanka", "nepal",
        "印度", "巴基斯坦", "孟加拉", "斯里兰卡", "尼泊尔",
    ),
    "Australia and New Zealand": ("australia", "new zealand", "澳大利亚", "澳洲", "新西兰"),
    "North America": ("united states", "usa", "us", "america", "canada", "美国", "加拿大"),
    "UK and Europe": (
        "united kingdom", "uk", "england", "britain", "germany", "france", "spain", "italy", "romania",
        "greece", "czechia", "czech republic", "hungary", "finland",
        "netherlands", "ireland", "portugal", "sweden", "norway", "denmark", "switzerland",
        "belgium", "austria", "poland", "europe",
        "英国", "德国", "法国", "西班牙", "意大利", "荷兰", "爱尔兰", "葡萄牙", "瑞典", "挪威", "丹麦",
        "瑞士", "比利时", "奥地利", "波兰", "欧洲", "罗马尼亚", "希腊", "捷克", "匈牙利", "芬兰",
    ),
    "Middle East": (
        "united arab emirates", "uae", "dubai", "saudi arabia", "qatar", "israel", "turkey",
        "kuwait", "bahrain", "oman", "jordan",
        "阿联酋", "迪拜", "沙特", "卡塔尔", "以色列", "土耳其", "科威特", "巴林", "阿曼", "约旦",
    ),
    "Latin America": (
        "brazil", "mexico", "argentina", "chile", "colombia", "peru",
        "巴西", "墨西哥", "阿根廷", "智利", "哥伦比亚", "秘鲁",
    ),
    "Africa": (
        "nigeria", "kenya", "south africa", "egypt", "ghana", "morocco", "ethiopia",
        "尼日利亚", "肯尼亚", "南非", "埃及", "加纳", "摩洛哥", "埃塞俄比亚",
    ),
}
_EXACT_ALIASES = {alias: region for region, aliases in _REGION_ALIASES.items() for alias in aliases}
# Longest first, so "印度尼西亚" (Indonesia) wins over "印度" (India). Latin aliases
# match whole words only, so "Romania" is not Oman and "Indiana" is not India.
_ALIAS_MATCHERS = sorted(
    (
        (re.compile(rf"\b{re.escape(alias)}\b") if alias.isascii() else alias, region, len(alias))
        for alias, region in _EXACT_ALIASES.items()
    ),
    key=lambda matcher: matcher[2],
    reverse=True,
)

_STOPWORDS = frozenset(
    "the and for with that this are was were you your our their they them about from have has had "
    "not but what which who how why when where will would can could should into than then there".split()
)


def country_to_region(country: Optional[str]) -> str:
    """Map a profile's country, in English or Chinese, to one of the report's regions."""
    normalized = (country or "").strip().lower()
    if not normalized:
        return UNKNOWN_REGION
    if normalized in _EXACT_ALIASES:
        return _EXACT_ALIASES[normalized]
    for matcher, region, _ in _ALIAS_MATCHERS:
        if (matcher in normalized) if isinstance(matcher, str) else matcher.search(normalized):
            return region
    return UNKNOWN_REGION


@dataclass(frozen=True)
class AgentInfo:
    agent_id: int
    name: str
    entity_type: str
    country: str
    region: str


@dataclass(frozen=True)
class ActivityRecord:
    platform: str
    round_num: int
    agent_id: int
    agent_name: str
    action_type: str
    text: str
    target_author: str
    target_text: str


@dataclass(frozen=True)
class SurveyAnswer:
    platform: str
    agent_id: int
    agent_name: str
    entity_type: str
    region: str
    response: str
    created_at: str


_INTENT_PATTERN = re.compile(
    r"^[\s*_]*(?:answers?\s*[:\-]\s*)?(?:q(?:uestion)?\s*)?1\s*[.):][\s*_]*(yes|maybe|no)\b",
    re.IGNORECASE | re.MULTILINE,
)


def parse_intent(response: str) -> str:
    """YES, MAYBE or NO from a survey answer whose first question starts with one of them; '' otherwise."""
    match = _INTENT_PATTERN.search(response or "")
    return match.group(1).upper() if match else ""


def _query_terms(query: str) -> List[str]:
    words = re.findall(r"[\w$]+", (query or "").lower())
    return [w for w in dict.fromkeys(words) if (len(w) >= 3 or not w.isascii()) and w not in _STOPWORDS]


def _match_score(terms: Iterable[str], text: str) -> int:
    lowered = (text or "").lower()
    words = re.findall(r"[\w$]+", lowered)
    score = 0
    for term in terms:
        if term.isascii():
            score += any(word.startswith(term) for word in words)
        else:
            score += term in lowered
    return score


def _read_json(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        logger.warning(f"Could not read {path}: {error}")
        return None


class SimulationActivityStore:
    """Read-only view of one simulation's agents, actions, posts and survey answers."""

    def __init__(self, sim_dir: str):
        self.sim_dir = sim_dir
        self.agents: Dict[int, AgentInfo] = self._load_agents()
        self._records: Optional[List[ActivityRecord]] = None

    @classmethod
    def for_simulation(cls, simulation_id: str) -> "SimulationActivityStore":
        return cls(os.path.join(Config.OASIS_SIMULATION_DATA_DIR, simulation_id))

    # ── loading ──

    def _load_agents(self) -> Dict[int, AgentInfo]:
        config = _read_json(os.path.join(self.sim_dir, "simulation_config.json")) or {}
        profiles = _read_json(os.path.join(self.sim_dir, "reddit_profiles.json")) or []
        countries = {
            p.get("user_id"): str(p.get("country") or "")
            for p in profiles
            if isinstance(p, dict)
        }
        agents = {}
        for cfg in config.get("agent_configs", []):
            agent_id = cfg.get("agent_id")
            if agent_id is None:
                continue
            country = countries.get(agent_id, "")
            agents[agent_id] = AgentInfo(
                agent_id=agent_id,
                name=str(cfg.get("entity_name") or f"agent_{agent_id}"),
                entity_type=str(cfg.get("entity_type") or "Unknown"),
                country=country,
                region=country_to_region(country),
            )
        return agents

    def _db_path(self, platform: str) -> str:
        return os.path.join(self.sim_dir, f"{platform}_simulation.db")

    def _query_db(self, platform: str, sql: str) -> List[tuple]:
        path = self._db_path(platform)
        if not os.path.exists(path):
            return []
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                return con.execute(sql).fetchall()
            finally:
                con.close()
        except sqlite3.Error as error:
            logger.warning(f"Could not query {path}: {error}")
            return []

    def _author_name(self, agent_id: Optional[int], fallback: str) -> str:
        agent = self.agents.get(agent_id) if agent_id is not None else None
        return agent.name if agent else (fallback or "unknown")

    def _comment_targets(self, platform: str) -> Dict[int, Tuple[str, str]]:
        rows = self._query_db(
            platform,
            "SELECT c.comment_id, u.agent_id, u.name, p.content, p.quote_content "
            "FROM comment c JOIN post p ON p.post_id = c.post_id "
            "LEFT JOIN user u ON u.user_id = p.user_id",
        )
        return {
            comment_id: (self._author_name(agent_id, name), quote or content or "")
            for comment_id, agent_id, name, content, quote in rows
        }

    def records(self) -> List[ActivityRecord]:
        """Every agent action on both platforms, in log order, round events excluded."""
        if self._records is None:
            self._records = [r for platform in PLATFORMS for r in self._read_platform(platform)]
        return list(self._records)

    def _read_platform(self, platform: str) -> List[ActivityRecord]:
        path = os.path.join(self.sim_dir, platform, "actions.jsonl")
        if not os.path.exists(path):
            return []
        comment_targets = self._comment_targets(platform)
        records = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(entry, dict) or "action_type" not in entry:
                        continue
                    record = self._to_record(platform, entry, comment_targets)
                    if record is not None:
                        records.append(record)
        except OSError as error:
            logger.warning(f"Could not read {path}: {error}")
        return records

    @staticmethod
    def _to_record(
        platform: str, entry: Dict[str, Any], comment_targets: Dict[int, Tuple[str, str]]
    ) -> Optional[ActivityRecord]:
        try:
            agent_id = int(entry["agent_id"])
            round_num = int(entry.get("round") or 0)
        except (KeyError, TypeError, ValueError):
            return None
        args = entry.get("action_args")
        if not isinstance(args, dict):
            args = {}
        action_type = entry["action_type"]
        text, target_author, target_text = "", "", ""
        if action_type == "CREATE_POST":
            text = args.get("content", "")
        elif action_type == "QUOTE_POST":
            text = args.get("quote_content", "")
            target_author, target_text = args.get("original_author_name", ""), args.get("original_content", "")
        elif action_type == "REPOST":
            target_author, target_text = args.get("original_author_name", ""), args.get("original_content", "")
        elif action_type == "CREATE_COMMENT":
            text = args.get("content", "")
            target_author, target_text = comment_targets.get(args.get("comment_id"), ("", ""))
        elif action_type in ("LIKE_POST", "DISLIKE_POST"):
            target_author, target_text = args.get("post_author_name", ""), args.get("post_content", "")
        elif action_type in ("LIKE_COMMENT", "DISLIKE_COMMENT"):
            target_author, target_text = args.get("comment_author_name", ""), args.get("comment_content", "")
        elif action_type == "FOLLOW":
            target_author = args.get("target_user_name", "")
        elif action_type in ("SEARCH_POSTS", "SEARCH_USER"):
            text = args.get("query", "")
        return ActivityRecord(
            platform=platform,
            round_num=round_num,
            agent_id=agent_id,
            agent_name=str(entry.get("agent_name", "")),
            action_type=action_type,
            text=str(text or ""),
            target_author=str(target_author or ""),
            target_text=str(target_text or ""),
        )

    # ── queries ──

    def search(
        self,
        query: str,
        limit: int = 10,
        platform: Optional[str] = None,
        segment: Optional[str] = None,
        region: Optional[str] = None,
    ) -> List[ActivityRecord]:
        """Posts, quotes and comments whose own words best match the query."""
        terms = _query_terms(query)
        if not terms:
            return []
        scored = []
        for record in self.records():
            if record.action_type not in WRITTEN_ACTIONS:
                continue
            if platform and record.platform != platform:
                continue
            agent = self.agents.get(record.agent_id)
            if segment and (not agent or agent.entity_type.lower() != segment.lower()):
                continue
            if region and (not agent or agent.region.lower() != region.lower()):
                continue
            score = _match_score(terms, record.text)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1].round_num, pair[1].platform))
        return [record for _, record in scored[:limit]]

    def statistics(self, top_n: int = 10) -> Dict[str, Any]:
        """How the run went: volume by platform, round, segment and region, plus the posts that drew most reaction."""
        records = [r for r in self.records() if not self.agents or r.agent_id in self.agents]
        active = [r for r in records if r.action_type != IDLE_ACTION]
        active_ids = {r.agent_id for r in active}

        max_round = max((r.round_num for r in records), default=-1)
        per_round = Counter((r.round_num, r.platform) for r in active)
        rounds = [
            {"round": n, **{p: per_round[(n, p)] for p in PLATFORMS}}
            for n in range(max_round + 1)
        ]

        actions_by_agent = Counter(r.agent_id for r in active)
        written_by_agent = Counter(r.agent_id for r in active if r.action_type in WRITTEN_ACTIONS)

        def group_by(key: str) -> Dict[str, Dict[str, int]]:
            groups: Dict[str, Dict[str, int]] = defaultdict(
                lambda: {"agents": 0, "active_agents": 0, "actions": 0, "written": 0}
            )
            for agent in self.agents.values():
                group = groups[getattr(agent, key)]
                group["agents"] += 1
                group["active_agents"] += agent.agent_id in active_ids
                group["actions"] += actions_by_agent[agent.agent_id]
                group["written"] += written_by_agent[agent.agent_id]
            return dict(sorted(groups.items(), key=lambda item: -item[1]["actions"]))

        top_agents = [
            {
                "name": self._author_name(agent_id, ""),
                "segment": self.agents[agent_id].entity_type if agent_id in self.agents else "Unknown",
                "region": self.agents[agent_id].region if agent_id in self.agents else UNKNOWN_REGION,
                "actions": count,
                "written": written_by_agent[agent_id],
            }
            for agent_id, count in actions_by_agent.most_common(top_n)
        ]

        return {
            "total_actions": len(records),
            "idle_actions": len(records) - len(active),
            "by_platform": {p: sum(1 for r in records if r.platform == p) for p in PLATFORMS},
            "by_action_type": dict(Counter(r.action_type for r in records).most_common()),
            "total_agents": len(self.agents),
            "active_agents": len(active_ids),
            "rounds": rounds,
            "by_segment": group_by("entity_type"),
            "by_region": group_by("region"),
            "top_agents": top_agents,
            "top_posts": self._top_posts(top_n),
        }

    def _top_posts(self, limit: int) -> List[Dict[str, Any]]:
        posts = []
        for platform in PLATFORMS:
            comment_counts = dict(self._query_db(platform, "SELECT post_id, COUNT(*) FROM comment GROUP BY post_id"))
            rows = self._query_db(
                platform,
                "SELECT p.post_id, u.agent_id, u.name, p.content, p.quote_content, p.num_likes, p.num_shares "
                "FROM post p LEFT JOIN user u ON u.user_id = p.user_id",
            )
            for post_id, agent_id, name, content, quote, likes, shares in rows:
                text = quote or content or ""
                if not text:
                    continue
                agent = self.agents.get(agent_id)
                comments = comment_counts.get(post_id, 0)
                posts.append({
                    "platform": platform,
                    "author": self._author_name(agent_id, name),
                    "segment": agent.entity_type if agent else "Unknown",
                    "region": agent.region if agent else UNKNOWN_REGION,
                    "text": text,
                    "likes": likes or 0,
                    "shares": shares or 0,
                    "comments": comments,
                    "engagement": (likes or 0) + (shares or 0) + comments,
                })
        posts.sort(key=lambda p: -p["engagement"])
        return posts[:limit]

    def survey_answers(self, query: str = "", limit: int = 200, prompt_contains: str = "") -> List[SurveyAnswer]:
        """
        The latest interview answer from each agent on each platform.

        Ad-hoc interviews share the trace table with the survey, so pass a phrase
        from the survey's prompt as prompt_contains to keep only its answers.
        Traces without a response (a prompt that was never answered) are skipped.
        """
        answers = []
        for platform in PLATFORMS:
            rows = self._query_db(
                platform,
                "SELECT u.agent_id, t.user_id, t.info, t.created_at FROM trace t "
                "LEFT JOIN user u ON u.user_id = t.user_id "
                "WHERE t.action = 'interview' ORDER BY t.created_at",
            )
            latest: Dict[int, Tuple[str, str]] = {}
            for agent_id, user_id, info, created_at in rows:
                try:
                    payload = json.loads(info) if info else {}
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict) or not payload.get("response"):
                    continue
                if prompt_contains and prompt_contains.lower() not in str(payload.get("prompt", "")).lower():
                    continue
                response = payload["response"]
                key = agent_id if agent_id is not None else user_id
                latest[key] = (response if isinstance(response, str) else json.dumps(response, ensure_ascii=False),
                               str(created_at or ""))
            for agent_id, (response, created_at) in latest.items():
                agent = self.agents.get(agent_id)
                answers.append(SurveyAnswer(
                    platform=platform,
                    agent_id=agent_id,
                    agent_name=agent.name if agent else f"agent_{agent_id}",
                    entity_type=agent.entity_type if agent else "Unknown",
                    region=agent.region if agent else UNKNOWN_REGION,
                    response=response,
                    created_at=created_at,
                ))
        terms = _query_terms(query)
        if terms:
            answers = [a for a in answers if _match_score(terms, a.response)]
        return answers[:limit]


# ── text for the ReportAgent ──

def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_search_results(records: List[ActivityRecord], agents: Dict[int, AgentInfo]) -> str:
    if not records:
        return "No matching posts or comments were found in the simulation."
    lines = [f"{len(records)} matching posts/comments from the simulation (exact text, quote as written):"]
    for i, record in enumerate(records, 1):
        agent = agents.get(record.agent_id)
        who = f"{record.agent_name} ({agent.entity_type}, {agent.region})" if agent else record.agent_name
        kind = {"CREATE_POST": "post", "QUOTE_POST": "quote", "CREATE_COMMENT": "comment"}.get(record.action_type, record.action_type)
        lines.append(f"{i}. [{record.platform}, round {record.round_num}, {kind}] {who}: \"{_clip(record.text, 700)}\"")
        if record.target_author or record.target_text:
            lines.append(f"   replying to {record.target_author or 'a post'}: \"{_clip(record.target_text, 200)}\"")
    return "\n".join(lines)


def format_statistics(stats: Dict[str, Any]) -> str:
    lines = [
        f"Total actions: {stats['total_actions']} "
        f"(twitter {stats['by_platform'].get('twitter', 0)}, reddit {stats['by_platform'].get('reddit', 0)}); "
        f"idle (DO_NOTHING): {stats['idle_actions']}",
        f"Agents: {stats['active_agents']} of {stats['total_agents']} took at least one real action",
        "Action types: " + ", ".join(f"{k} {v}" for k, v in stats["by_action_type"].items()),
        "Activity per round (twitter/reddit, idle excluded): "
        + ", ".join(f"r{r['round']} {r['twitter']}/{r['reddit']}" for r in stats["rounds"]),
    ]
    for title, key in (("By segment", "by_segment"), ("By region", "by_region")):
        lines.append(f"{title} (agents, active agents, actions, posts+comments written):")
        lines.extend(
            f"- {name}: {g['agents']}, {g['active_agents']}, {g['actions']}, {g['written']}"
            for name, g in stats[key].items()
        )
    lines.append("Most active agents:")
    lines.extend(
        f"- {a['name']} ({a['segment']}, {a['region']}): {a['actions']} actions, {a['written']} written"
        for a in stats["top_agents"]
    )
    lines.append("Posts that drew the most reaction (likes + shares + comments):")
    lines.extend(
        f"- [{p['platform']}] {p['author']} ({p['segment']}, {p['region']}), "
        f"{p['likes']} likes, {p['shares']} shares, {p['comments']} comments: \"{_clip(p['text'], 240)}\""
        for p in stats["top_posts"]
    )
    return "\n".join(lines)


def format_survey_answers(answers: List[SurveyAnswer]) -> str:
    if not answers:
        return "No survey answers were found. The survey may not have been run for this simulation."
    lines = [f"{len(answers)} survey answers (latest per agent and platform):"]
    for answer in answers:
        lines.append(
            f"--- {answer.agent_name} ({answer.entity_type}, {answer.region}, {answer.platform}):\n"
            f"{_clip(answer.response, 1500)}"
        )
    return "\n".join(lines)
