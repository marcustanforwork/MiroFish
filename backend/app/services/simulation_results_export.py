"""
Export a finished simulation as small JSON datasets for a results dashboard.

Each file is a JSON array of row objects: run totals, activity per round,
breakdowns by segment and region, the action mix, the posts that drew most
reaction, the most active agents, survey answers with their YES/MAYBE/NO,
and (when a report exists) the report's title, summary and section leads.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

from .simulation_activity import SimulationActivityStore, parse_intent

_SIM_MODEL_PATTERN = re.compile(r"\[SIM\] model=([^,\s]+)")


def _agent_model(sim_dir: str) -> str:
    """The agents' model as the runner logged it (the LLM_SIM_MODEL_NAME patch)."""
    path = os.path.join(sim_dir, "simulation.log")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                match = _SIM_MODEL_PATTERN.search(line)
                if match:
                    return match.group(1)
    except FileNotFoundError:
        pass
    return ""


def _lead_paragraph(markdown: str, limit: int = 600) -> str:
    """The first paragraph of plain prose: no heading, bold label, quote or list."""
    for block in re.split(r"\n\s*\n", markdown or ""):
        text = block.strip()
        if not text or text.startswith(("#", ">", "- ", "* ", "|")):
            continue
        if re.fullmatch(r"\*\*[^*]+\*\*", text):
            continue
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 1] + "…"
    return ""


def _report_sections(report_dir: str) -> List[Dict[str, Any]]:
    with open(os.path.join(report_dir, "outline.json"), "r", encoding="utf-8") as f:
        outline = json.load(f)
    rows = [{"order": 0, "title": outline.get("title", ""), "lead": outline.get("summary", "")}]
    for index, section in enumerate(outline.get("sections", []), 1):
        path = os.path.join(report_dir, f"section_{index:02d}.md")
        markdown = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                markdown = f.read()
        rows.append({"order": index, "title": section.get("title", ""), "lead": _lead_paragraph(markdown)})
    return rows


def _write(out_dir: str, name: str, rows: List[Dict[str, Any]]) -> str:
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    return name


def export_results(
    store: SimulationActivityStore,
    out_dir: str,
    report_dir: Optional[str] = None,
    label: str = "",
    top_n: int = 15,
) -> List[str]:
    """Write the dashboard datasets for one simulation into out_dir; returns the file names written."""
    os.makedirs(out_dir, exist_ok=True)
    stats = store.statistics(top_n=top_n)
    answers = store.survey_answers()

    def breakdown(key: str, column: str) -> List[Dict[str, Any]]:
        return [{column: name, **counts} for name, counts in stats[key].items()]

    written_total = sum(g["written"] for g in stats["by_segment"].values())
    kpis = [{
        "label": label,
        "agent_model": _agent_model(store.sim_dir),
        "rounds": max((r["round"] for r in stats["rounds"]), default=0),
        "total_agents": stats["total_agents"],
        "active_agents": stats["active_agents"],
        "total_actions": stats["total_actions"],
        "idle_actions": stats["idle_actions"],
        "idle_share": stats["idle_actions"] / stats["total_actions"] if stats["total_actions"] else 0,
        "written": written_total,
        "twitter_actions": stats["by_platform"].get("twitter", 0),
        "reddit_actions": stats["by_platform"].get("reddit", 0),
        "survey_answers": len(answers),
    }]

    files = [
        _write(out_dir, "kpis.json", kpis),
        _write(out_dir, "rounds.json", stats["rounds"]),
        _write(out_dir, "segments.json", breakdown("by_segment", "segment")),
        _write(out_dir, "regions.json", breakdown("by_region", "region")),
        _write(out_dir, "action_types.json",
               [{"action_type": k, "count": v} for k, v in stats["by_action_type"].items()]),
        _write(out_dir, "top_posts.json",
               [{"rank": i, **post} for i, post in enumerate(stats["top_posts"], 1)]),
        _write(out_dir, "top_agents.json",
               [{"rank": i, **agent} for i, agent in enumerate(stats["top_agents"], 1)]),
        _write(out_dir, "survey.json", [
            {
                "platform": a.platform, "agent": a.agent_name, "segment": a.entity_type,
                "region": a.region, "intent": parse_intent(a.response), "answer": a.response,
            }
            for a in answers
        ]),
    ]
    if report_dir and os.path.exists(os.path.join(report_dir, "outline.json")):
        files.append(_write(out_dir, "report_sections.json", _report_sections(report_dir)))
    return files
