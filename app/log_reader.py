import re
from pathlib import Path


def find_log_file(experiment_dir: Path) -> Path | None:
    """Find experiment.log inside an experiment dir (checks sub-run dirs)."""
    if not experiment_dir or not experiment_dir.exists():
        return None
    logs = list(experiment_dir.rglob("experiment.log"))
    return logs[0] if logs else None


def read_log_tail(log_path: Path, chars: int = 8000) -> str:
    """Read the last N characters from a log file."""
    if not log_path or not log_path.exists():
        return "(no log file found)"
    try:
        text = log_path.read_text(errors="replace")
        return text[-chars:] if len(text) > chars else text
    except OSError:
        return "(error reading log)"


def read_log_incremental(log_path: Path, offset: int) -> tuple[str, int]:
    """
    Read new content from log_path starting at byte offset.
    Returns (new_content, new_offset).
    """
    if not log_path or not log_path.exists():
        return "", offset
    try:
        with open(log_path, "r", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()
        return new_content, new_offset
    except OSError:
        return "", offset


# Patterns for progress extraction
_JUDGE_EVAL_SAVED_RE = re.compile(r"Saved judge evaluation to .+judge_evaluation\.json", re.IGNORECASE)
_EFFECTIVENESS_RE = re.compile(r"Mitigation effectiveness:\s*([\d.]+)%", re.IGNORECASE)

_PHASE_PATTERNS = [
    (re.compile(r"Starting initial vulnerability"), "Running initial attack"),
    (re.compile(r"Initial vulnerability testing complete"), "Baseline attack done"),
    (re.compile(r"Suggester|mitigation_suggester", re.IGNORECASE), "Suggester proposing"),
    (re.compile(r"Implementer|mitigation_implementer", re.IGNORECASE), "Implementer executing"),
    (re.compile(r"Critic|critic", re.IGNORECASE), "Critic validating"),
    (re.compile(r"Running mitigation validation|Validation|caldera", re.IGNORECASE), "Running validation"),
    (re.compile(r"Saved context for judge", re.IGNORECASE), "Judge evaluating"),
    (re.compile(r"mitigation_outcome", re.IGNORECASE), "Mitigation scored"),
    (re.compile(r"Summarizer|summary", re.IGNORECASE), "Generating summary"),
    (re.compile(r"Experiment complete|run complete|finished", re.IGNORECASE), "Completed"),
]


def parse_log_progress(log_text: str) -> dict:
    """
    Scan log text and extract:
    - mitigations_tried: judge context files saved
    - mitigations_succeeded: count of 'success' outcomes
    - mitigations_failed: count of 'failure' outcomes
    - current_phase: last meaningful phase detected
    """
    tried = len(_JUDGE_EVAL_SAVED_RE.findall(log_text))
    # Any effectiveness > 0% counts as at least partial success for display
    effectiveness_values = [float(m) for m in _EFFECTIVENESS_RE.findall(log_text)]
    succeeded = sum(1 for e in effectiveness_values if e > 0.0)
    failed = sum(1 for e in effectiveness_values if e == 0.0)

    current_phase = "Initializing"
    for line in log_text.splitlines():
        for pattern, phase_name in _PHASE_PATTERNS:
            if pattern.search(line):
                current_phase = phase_name

    return {
        "mitigations_tried": tried,
        "mitigations_succeeded": succeeded,
        "mitigations_failed": failed,
        "current_phase": current_phase,
    }
