import json
import re
from datetime import datetime
from pathlib import Path

from json_repair import repair_json

from app.config import load_json, sorted_mitigation_dirs

AGENT_AVATARS = {
    "mitigation_suggester": "💡",
    "mitigation_implementer": "🔧",
    "critic": "🔍",
    "judge": "⚖️",
    "single_agent": "🤖",
    "shieldgpt_agent": "🛡",
    "summarizer": "📝",
    "user": "👤",
}

_TS_RE = re.compile(r"(\d{8})_(\d{6})(?:_\d+)?\.json$")


def _extract_file_timestamp(path: Path) -> datetime:
    """Parse YYYYMMDD_HHMMSS from filename for sorting."""
    m = _TS_RE.search(path.name)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
        except ValueError:
            pass
    return datetime.min


_RESPONSE_KEYS = {
    "chosen_mitigation", "suggestions",            # suggester
    "mitigation_currently_implemented", "comments", # implementer
    "comment", "approved",                          # critic
    "overall_assessment", "mitigation_outcome",     # judge
    "mitigation_suggested", "critique",             # single agent
}


def _try_parse_json(content) -> dict | None:
    """
    Try to parse content as JSON (with repair). Returns dict or None.

    Agents sometimes emit multiple concatenated JSON objects in one response
    (e.g. the implementer writes a summary object followed by per-tool-call
    objects). json_repair turns these into a list. We pick the first dict
    that contains recognised top-level keys.
    """
    if isinstance(content, dict):
        return content
    s = str(content).strip()
    if not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        result = json.loads(repair_json(s))
    except Exception:
        return None

    if isinstance(result, dict):
        return result

    if isinstance(result, list):
        # Find the first dict with a known response key
        for item in result:
            if isinstance(item, dict) and _RESPONSE_KEYS & item.keys():
                return item
        # Fall back to first dict
        for item in result:
            if isinstance(item, dict):
                return item

    return None


def _match_tool_calls(mitigation_dir: Path, agent_name: str, context_file: Path) -> list[dict]:
    """
    Return tool calls from the tool_calls file whose timestamp matches this context file.
    Matches on YYYYMMDD_HHMMSS (ignores microseconds so the pair is found even if they
    differ by a few hundred microseconds).
    """
    m = _TS_RE.search(context_file.name)
    if not m:
        return []
    ts_prefix = f"{m.group(1)}_{m.group(2)}"
    for p in mitigation_dir.glob(f"{agent_name}_tool_calls_{ts_prefix}*.json"):
        data = load_json(p)
        if data:
            return data.get("tool_calls", [])
    return []


def _load_judge_extra(mitigation_dir: Path) -> dict:
    """Load validation_results.json and operation report for the judge renderer."""
    val_results = load_json(mitigation_dir / "validation_results.json")

    op_report = None
    captures_dir = mitigation_dir / "validation_captures"
    if captures_dir.exists():
        for f in captures_dir.glob("*_operation_report.json"):
            op_report = load_json(f)
            break

    return {"validation_results": val_results, "operation_report": op_report}


def load_conversation_turns(mitigation_dir: Path) -> list[dict]:
    """
    Load all *_context_*.json files from a mitigation dir, sorted chronologically.

    Each agent context file contains the FULL accumulated message history up to
    that agent's turn, so rendering input_messages from every file would repeat
    all previous agents' outputs.  Instead we:
      1. From the FIRST context file only: emit the initial user context messages.
      2. From EVERY file: emit the agent's own response.

    This gives the correct linear flow:
      User (context) → Suggester → Implementer → [Critic → Implementer]* → Judge
    """
    if not mitigation_dir or not mitigation_dir.exists():
        return []

    context_files = sorted(mitigation_dir.glob("*_context_*.json"), key=_extract_file_timestamp)
    if not context_files:
        return []

    turns = []

    for file_idx, cf in enumerate(context_files):
        data = load_json(cf)
        if not data:
            continue

        agent_name = data.get("agent_name", cf.stem.split("_context_")[0])
        mit_n = data.get("mitigations_counter", 0)
        ts = data.get("timestamp", "")
        token_usage = data.get("token_usage", {})
        avatar = AGENT_AVATARS.get(agent_name, "🤖")

        # ── Initial user context (first file only) ──────────────────────────
        # The first agent (suggester) receives the system context as user messages.
        # We show these once so the reader knows what information was given.
        if file_idx == 0:
            for msg in data.get("input_messages", []):
                source = msg.get("source", "user")
                if source != "user":
                    continue  # skip non-user messages even in the first file
                content = msg.get("content", "")
                if not content:
                    continue
                if len(content) > 6000:
                    content = content[:6000] + "\n\n*...[truncated]*"
                content_md = content
                turns.append({
                    "agent": "user",
                    "avatar": AGENT_AVATARS["user"],
                    "timestamp": ts,
                    "mitigation_n": mit_n,
                    "source": "user",
                    "parsed_json": None,
                    "raw_content": content_md,
                    "token_usage": None,
                    "tool_calls": [],
                    "is_response": False,
                    "context_file": cf.name,
                })

        # ── Agent response ───────────────────────────────────────────────────
        resp = data.get("response", {})
        content = resp.get("content", "") if isinstance(resp, dict) else str(resp)
        if not content:
            continue

        parsed_json = _try_parse_json(content)

        # Tool calls: match to this specific invocation by timestamp
        tool_calls = _match_tool_calls(mitigation_dir, agent_name, cf)

        # For the judge, also attach validation results and operation report
        extra_data = _load_judge_extra(mitigation_dir) if agent_name == "judge" else {}

        turns.append({
            "agent": agent_name,
            "avatar": avatar,
            "timestamp": ts,
            "mitigation_n": mit_n,
            "source": agent_name,
            "parsed_json": parsed_json,
            "raw_content": str(content),
            "token_usage": token_usage,
            "tool_calls": tool_calls,
            "extra_data": extra_data,
            "is_response": True,
            "context_file": cf.name,
        })

    return turns


def collect_all_judge_scores(sub_run_dir: Path) -> list[dict]:
    """
    Collect summary rows from all single_mitigation_{N}/judge_evaluation.json files.
    Returns a list of flat dicts for tabular display.
    """
    rows = []
    single_dir = sub_run_dir / "single"
    if not single_dir.exists():
        # Older layout: mitigation dirs directly under sub_run_dir
        single_dir = sub_run_dir

    for mit_dir in sorted_mitigation_dirs(single_dir):
        eval_data = load_json(mit_dir / "judge_evaluation.json")
        if not eval_data:
            continue

        assessment = eval_data.get("overall_assessment", {})
        kpis = eval_data.get("multi_agent_kpis", {})
        agent_scores = eval_data.get("agent_scores", {})

        # Compute average agent score across all agents and criteria
        all_scores = []
        for agent, criteria in agent_scores.items():
            for kpi, kpi_data in criteria.items():
                if isinstance(kpi_data, dict) and "score" in kpi_data:
                    all_scores.append(kpi_data["score"])
        avg_score = sum(all_scores) / len(all_scores) if all_scores else None

        row = {
            "mitigation": mit_dir.name,
            "outcome": assessment.get("mitigation_outcome", "unknown"),
            "effectiveness": f"{eval_data.get('mitigation_effectiveness', 0) * 100:.0f}%",
            "baseline_rate": f"{eval_data.get('baseline_success_rate', 0) * 100:.0f}%",
            "current_rate": f"{eval_data.get('current_success_rate', 0) * 100:.0f}%",
            "category": eval_data.get("mitigation_category", ""),
            "avg_score": f"{avg_score:.1f}/10" if avg_score is not None else "N/A",
            "task_completion": kpis.get("task_completion_rate", {}).get("score", None),
            "communication": kpis.get("inter_agent_communication_efficiency", {}).get("score", None),
            "time_saved": kpis.get("time_saved_for_humans", {}).get("score", None),
        }
        rows.append(row)
    return rows


def collect_cross_experiment_scores(experiments: list[Path]) -> list[dict]:
    """Aggregate judge scores across multiple experiments for comparison."""
    rows = []
    for exp_dir in experiments:
        config = load_json(exp_dir / "config.json") or {}
        for sub_run in (p for p in exp_dir.iterdir() if p.is_dir()):
            sub_scores = collect_all_judge_scores(sub_run)
            if not sub_scores:
                continue
            successes = sum(1 for r in sub_scores if r["outcome"] == "success")
            avg_scores = []
            for r in sub_scores:
                try:
                    avg_scores.append(float(r["avg_score"].split("/")[0]))
                except (ValueError, AttributeError):
                    pass
            rows.append({
                "experiment": exp_dir.name,
                "sub_run": sub_run.name,
                "mitigations": len(sub_scores),
                "successes": successes,
                "success_rate": f"{successes / len(sub_scores) * 100:.0f}%" if sub_scores else "N/A",
                "avg_judge_score": f"{sum(avg_scores) / len(avg_scores):.1f}" if avg_scores else "N/A",
            })
    return rows
