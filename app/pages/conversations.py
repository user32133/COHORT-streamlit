import re
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import streamlit as st

from app.config import list_experiments, list_sub_runs, load_json, sorted_mitigation_dirs
from app.data_parser import AGENT_AVATARS, load_conversation_turns
from app.renderers import render_agent_message


def _collect_cumulative_progression(master_dir: Path, selected_mit_num: int | None = None):
    """
    Walk master_mitigation_* dirs and build the cumulative effectiveness
    progression, filtering out mitigations that worsened attack success rate
    or had dead agents.

    Returns list of dicts: {step, mit_number, current_success_rate, effectiveness, label}
    """
    mit_dirs = sorted(
        master_dir.glob("master_mitigation_*"),
        key=lambda p: int(re.search(r"(\d+)$", p.name).group(1)),
    )

    baseline = None
    last_best_rate = None
    progression = []
    step = 0

    for mit_dir in mit_dirs:
        n = int(re.search(r"(\d+)$", mit_dir.name).group(1))

        # Stop at the selected mitigation — don't show future ones
        if selected_mit_num is not None and n > selected_mit_num:
            break

        vr = load_json(mit_dir / "validation_results.json")
        if not vr or not vr.get("validation_completed", True):
            continue

        if baseline is None:
            baseline = vr.get("baseline_success_rate")
            if baseline is None:
                continue
            last_best_rate = baseline
            progression.append({
                "step": 0,
                "mit_number": None,
                "current_success_rate": baseline,
                "effectiveness": 0.0,
                "label": "Baseline",
            })

        current_rate = vr.get("current_success_rate", 1.0)
        eff = vr.get("mitigation_effectiveness", 0.0)

        # Skip if this mitigation worsened the cumulative attack success rate
        if current_rate > last_best_rate:
            continue

        # Skip if the agent was dead and never ran validity checks
        validity_checks = vr.get("validity_checks", {})
        all_dead = bool(validity_checks) and all(
            c.get("status") == -3 and c.get("run") is None
            for c in validity_checks.values()
            if isinstance(c, dict)
        )
        if all_dead:
            continue

        step += 1
        last_best_rate = current_rate
        progression.append({
            "step": step,
            "mit_number": n,
            "current_success_rate": current_rate,
            "effectiveness": eff,
            "label": f"Mit #{n}",
        })

    return progression


def _render_cumulative_chart(progression: list[dict], selected_mit_num: int | None = None):
    """Render the cumulative effectiveness matplotlib chart into Streamlit."""
    if len(progression) < 2:
        return

    color = "#2196F3"
    highlight_color = "#FF5722"

    fig, ax = plt.subplots(figsize=(8, 4.5))

    steps = [p["step"] for p in progression]
    effectiveness = [p["effectiveness"] * 100 for p in progression]
    labels = [p["label"] for p in progression]
    mit_numbers = [p["mit_number"] for p in progression]

    # Shaded step area
    ax.step(steps, effectiveness, where="post", color=color, linewidth=2, alpha=0.35)
    ax.fill_between(steps, effectiveness, alpha=0.07, color=color, step="post")

    # Connected line + markers (highlight selected mitigation)
    for i, (s, e, lbl, mn) in enumerate(zip(steps, effectiveness, labels, mit_numbers)):
        is_selected = mn == selected_mit_num
        mc = highlight_color if is_selected else color
        msize = 13 if is_selected else 10
        mew = 3.0 if is_selected else 2.5
        ax.plot(s, e, color=mc, marker="o", markersize=msize,
                markerfacecolor="white", markeredgewidth=mew, zorder=5)

        va = "bottom"
        y_offset = 10
        if e > 80:
            va = "top"
            y_offset = -14
        ax.annotate(
            f"{lbl}\n{e:.0f}%",
            xy=(s, e),
            xytext=(0, y_offset),
            textcoords="offset points",
            ha="center", va=va,
            fontsize=9, color=mc, fontweight="bold",
        )

    # Connect points with a line
    ax.plot(steps, effectiveness, color=color, linewidth=2.5, zorder=4)

    # 100% reference line
    ax.axhline(100, color="gray", linewidth=0.8, linestyle="--", alpha=0.5)

    ax.set_xlabel("Successful master mitigations applied", fontsize=10)
    ax.set_ylabel("Cumulative mitigation effectiveness (%)", fontsize=10)
    ax.set_ylim(-5, 110)
    ax.set_xlim(-0.4, max(steps) + 0.6)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%d%%"))
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title("Cumulative Master Mitigation Effectiveness",
                 fontsize=12, fontweight="bold")

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)


def render_conversations_page():
    st.markdown(
        """
        <style>
        /* Enlarge font in chat message bubbles */
        .stChatMessage p,
        .stChatMessage li,
        .stChatMessage span,
        .stChatMessage div[data-testid="stMarkdownContainer"] {
            font-size: 1.3rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("Agent Conversations")

    # ── Experiment selector ──────────────────────────────────────────────────
    experiments = list_experiments()
    if not experiments:
        st.info("No experiments found in `experiments/`.")
        return

    # Filter to experiments that have at least one mitigation
    def _has_mitigations(exp_dir):
        for sub in list_sub_runs(exp_dir):
            single = sub / "single" if (sub / "single").exists() else sub
            if sorted_mitigation_dirs(single):
                return True
        return False

    experiments = [e for e in experiments if _has_mitigations(e)]
    if not experiments:
        st.info("No experiments with mitigation data found.")
        return

    exp_options = {e.name: e for e in experiments}

    # Pre-select the most recent experiment from the active/last run
    last = st.session_state.get("last_experiment_dir")
    default_exp = last.name if last and last.name in exp_options else list(exp_options.keys())[0]

    chosen_exp_name = st.selectbox(
        "Experiment",
        options=list(exp_options.keys()),
        index=list(exp_options.keys()).index(default_exp),
    )
    exp_dir = exp_options[chosen_exp_name]

    # ── Sub-run selector ─────────────────────────────────────────────────────
    sub_runs = list_sub_runs(exp_dir)
    if not sub_runs:
        st.info("No sub-runs found in this experiment.")
        return

    sub_run_options = {s.name: s for s in sub_runs}
    chosen_sub = st.selectbox("Sub-run", options=list(sub_run_options.keys()))
    sub_run_dir = sub_run_options[chosen_sub]

    # ── Mitigation selector ──────────────────────────────────────────────────
    # Try single/ subdir first (current format), then root dir (old format)
    single_dir = sub_run_dir / "single"
    if not single_dir.exists():
        single_dir = sub_run_dir

    mit_dirs = sorted_mitigation_dirs(single_dir)
    if not mit_dirs:
        st.info("No mitigation folders found yet.")
        return

    mit_options = {m.name: m for m in mit_dirs}
    chosen_mit = st.selectbox(
        "Mitigation",
        options=list(mit_options.keys()),
        format_func=lambda n: n.replace("_", " ").title(),
    )
    mit_dir = mit_options[chosen_mit]

    # ── Load turns ────────────────────────────────────────────────────────────
    turns = load_conversation_turns(mit_dir)

    if not turns:
        st.info("No conversation data found for this mitigation.")
        return

    # ── Agent filter ──────────────────────────────────────────────────────────
    all_agents = sorted({t["agent"] for t in turns})
    selected_agents = st.multiselect(
        "Show agents",
        options=all_agents,
        default=all_agents,
    )

    st.divider()

    # ── Render chat turns ─────────────────────────────────────────────────────
    for turn in turns:
        if turn["agent"] not in selected_agents:
            continue

        is_response = turn["is_response"]
        role = "assistant" if is_response else "user"
        avatar = turn.get("avatar") or AGENT_AVATARS.get(turn["agent"], "🤖")

        with st.chat_message(role, avatar=avatar):
            agent_label = turn["agent"].replace("_", " ").title()
            ts = turn.get("timestamp", "")
            ts_short = ts[:19] if len(ts) >= 19 else ts
            st.caption(f"**{agent_label}** · {ts_short}")

            # ── Message body ──────────────────────────────────────────────
            if is_response and turn.get("parsed_json"):
                render_agent_message(
                    turn["agent"],
                    turn["parsed_json"],
                    tool_calls=turn.get("tool_calls"),
                    extra_data=turn.get("extra_data"),
                )
            else:
                # User context or unrecognised plain text
                raw = turn.get("raw_content", "")
                if len(raw) > 6000:
                    raw = raw[:6000] + "\n\n*...[truncated]*"
                st.markdown(raw)

            # ── Token usage ───────────────────────────────────────────────
            if is_response and turn.get("token_usage"):
                tok = turn["token_usage"]
                in_tok = tok.get("prompt_tokens", 0)
                out_tok = tok.get("completion_tokens", 0)
                st.caption(f"Tokens: {in_tok:,} in / {out_tok:,} out")

    # ── Master (cumulative) mitigation results ───────────────────────────────
    # Find the matching master_mitigation_N for the selected single_mitigation_N
    m = re.search(r"_(\d+)$", chosen_mit)
    if m:
        mit_num = m.group(1)
        master_dir = sub_run_dir / "master" / f"master_mitigation_{mit_num}"
        if master_dir.exists():
            st.divider()
            st.subheader(f"Cumulative Mitigation Results (master_mitigation_{mit_num})")
            st.caption(
                "This shows the validation results when **all mitigations up to this point** "
                "are applied together."
            )

            # ── Applied mitigations summary ──────────────────────────────
            applied = load_json(master_dir / "applied_mitigations.json")
            if applied:
                total = applied.get("total_applied", 0)
                mitigations_list = applied.get("mitigations", [])
                st.markdown(f"**Total mitigations applied cumulatively:** {total}")
                if mitigations_list:
                    with st.expander(
                        f"Applied mitigations ({len(mitigations_list)})", expanded=False
                    ):
                        for mit in mitigations_list:
                            num = mit.get("mitigation_number", "?")
                            name = mit.get("mitigation_name", "Unknown")
                            st.markdown(f"**{num}.** {name}")

            # ── Validation results ───────────────────────────────────────
            val_results = load_json(master_dir / "validation_results.json")
            if val_results:
                baseline = val_results.get("baseline_success_rate")
                current = val_results.get("current_success_rate")
                effectiveness = val_results.get("mitigation_effectiveness")
                is_mitigated = val_results.get("is_attack_mitigated")

                c1, c2, c3, c4 = st.columns(4)
                if baseline is not None:
                    c1.metric("Baseline attack rate", f"{baseline * 100:.0f}%")
                if current is not None:
                    delta = (
                        f"{(current - baseline) * 100:+.0f}%"
                        if baseline is not None
                        else None
                    )
                    c2.metric(
                        "Cumulative post-mitigation rate",
                        f"{current * 100:.0f}%",
                        delta=delta,
                        delta_color="inverse",
                    )
                if effectiveness is not None:
                    c3.metric("Cumulative effectiveness", f"{effectiveness * 100:.0f}%")
                if is_mitigated is not None:
                    c4.metric(
                        "Attack mitigated",
                        "Yes" if is_mitigated else "No",
                    )

                # ── Validity checks ──────────────────────────────────────
                validity_checks = val_results.get("validity_checks", {})
                if validity_checks:
                    st.markdown("**Validity checks (cumulative)**")
                    for check_name, check in validity_checks.items():
                        if not isinstance(check, dict):
                            continue
                        ok = check.get("success", False)
                        icon = "✅" if ok else "❌"
                        with st.expander(f"{icon} {check_name}", expanded=not ok):
                            desc = check.get("description", "")
                            if desc:
                                st.caption(desc)
                            stdout = check.get("stdout", "")
                            stderr = check.get("stderr", "")
                            if stdout:
                                st.code(stdout[:2000], language="text")
                            if stderr:
                                st.code(stderr[:2000], language="text")

            # ── Cumulative effectiveness chart ───────────────────────────
            progression = _collect_cumulative_progression(
                sub_run_dir / "master", selected_mit_num=int(mit_num)
            )
            if len(progression) >= 2:
                st.markdown("**Cumulative effectiveness progression**")
                _render_cumulative_chart(progression, selected_mit_num=int(mit_num))
