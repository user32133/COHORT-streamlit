import json
import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"
SRC_DIR = PROJECT_ROOT / "src"

SUPPORTED_MODEL_NAMES = [
    "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b",
    "openai/gpt-5-nano",
    "openai/gpt-5-mini",
    "openai/gpt-4.1-mini",
    "openai/gpt-5.4-mini",
    "google/gemini-2.0-flash-exp:free",
    "google/gemini-3-flash-preview",
    "google/gemini-2.5-pro",
    "x-ai/grok-4.1-fast",
    "deepseek/deepseek-v3.2",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-sonnet-4.5",
    "mistralai/mistral-small-3.1-24b-instruct:free",
    "mistralai/devstral-2512",
    "qwen/qwen3-4b:free",
    "qwen/qwen3-coder:free",
    "meta-llama/llama-3.3-70b-instruct:free",
]

SUPPORTED_TOPOLOGIES = ["small_enterprise", "medium_enterprise", "large_enterprise"]
SUPPORTED_PATTERNS = ["GraphFlow", "Single", "ShieldGPT"]
SUPPORTED_AGENTS = ["suggester", "implementer", "critic", "judge", "single", "shieldgpt", "summarizer"]


def list_experiments() -> list[Path]:
    """Return experiment dirs sorted newest-first."""
    if not EXPERIMENTS_DIR.exists():
        return []
    dirs = [p for p in EXPERIMENTS_DIR.iterdir() if p.is_dir() and p.name.startswith("experiment_")]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def list_sub_runs(exp_dir: Path) -> list[Path]:
    """List sub-run dirs inside an experiment (non-file children)."""
    if not exp_dir or not exp_dir.exists():
        return []
    return sorted([p for p in exp_dir.iterdir() if p.is_dir()])


def sorted_mitigation_dirs(single_dir: Path) -> list[Path]:
    """Sort single_mitigation_{N} dirs by N numerically."""
    if not single_dir or not single_dir.exists():
        return []

    def _mitigation_num(p: Path) -> int:
        m = re.search(r"_(\d+)$", p.name)
        return int(m.group(1)) if m else 0

    dirs = [p for p in single_dir.iterdir() if p.is_dir() and "mitigation" in p.name]
    return sorted(dirs, key=_mitigation_num)


def load_json(path: Path) -> dict | None:
    """Safe JSON loader."""
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(errors="replace"))
    except Exception:
        return None


def load_attacks_from_env() -> list[str]:
    """Read LINUX_SUPPORTED_ATTACKS from .env file."""
    env_path = PROJECT_ROOT / ".env"
    attacks = []
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("LINUX_SUPPORTED_ATTACKS="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                attacks = [a.strip() for a in val.split(",") if a.strip()]
                break
    # Fall back to environment variable
    if not attacks:
        env_val = os.getenv("LINUX_SUPPORTED_ATTACKS", "")
        if env_val:
            attacks = [a.strip() for a in env_val.split(",") if a.strip()]
    return attacks
