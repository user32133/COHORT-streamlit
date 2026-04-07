"""
Per-agent structured renderers for the Conversations page.
"""
import streamlit as st


def _score_bar(score: int | float, max_score: int = 10) -> str:
    filled = round(score)
    return "█" * filled + "░" * (max_score - filled) + f"  {score}/{max_score}"


# ── Suggester ─────────────────────────────────────────────────────────────────

def render_suggester(data: dict, **_):
    chosen = data.get("chosen_mitigation", "")
    suggestions = data.get("suggestions", [])

    if data.get("reached_mitigation_limit") or data.get("no_mitigation_left"):
        st.warning("No more mitigations to propose — limit reached.")
        return

    if chosen:
        st.markdown("**Chosen mitigation**")
        st.info(chosen)

    if suggestions:
        with st.expander(f"All suggestions ({len(suggestions)})", expanded=False):
            for i, s in enumerate(suggestions, 1):
                st.markdown(f"**{i}.** {s}")


# ── Implementer ───────────────────────────────────────────────────────────────

def render_implementer(data: dict, tool_calls: list = None, **_):
    mitigation = data.get("mitigation_currently_implemented", "")
    comments = data.get("comments", "")
    device = data.get("device_identifier", "")

    if device:
        st.markdown(f"**Device:** `{device}`")

    if mitigation:
        st.markdown("**Implementing**")
        st.info(mitigation)

    if comments:
        st.markdown(comments)

    # ── Tool call request/result pairs ────────────────────────────────────
    if tool_calls:
        # Group into (request, result) pairs by call_id
        by_id: dict[str, dict] = {}
        order: list[str] = []
        for tc in tool_calls:
            cid = tc.get("call_id", tc.get("id", str(id(tc))))
            if cid not in by_id:
                by_id[cid] = {}
                order.append(cid)
            if tc.get("type") == "request":
                by_id[cid]["request"] = tc
            else:
                by_id[cid]["result"] = tc

        with st.expander(f"Tool calls ({len(order)})", expanded=True):
            for cid in order:
                pair = by_id[cid]
                req = pair.get("request", {})
                res = pair.get("result", {})

                name = req.get("name", res.get("name", "unknown"))
                raw_args = req.get("arguments", "{}")
                # Parse args JSON string
                try:
                    import json as _json
                    args = _json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {"raw": raw_args}

                device_id = args.get("device_identifier", "")
                command = args.get("command", "")
                result_content = str(res.get("content", "")).strip()

                label = f"`{name}`" + (f" → `{device_id}`" if device_id else "")
                st.markdown(f"**{label}**")

                if command:
                    st.code(command, language="bash")

                if result_content:
                    # Truncate very long outputs
                    if len(result_content) > 2000:
                        result_content = result_content[:2000] + "\n...[truncated]"
                    st.code(result_content, language="text")

                st.markdown("---")


# ── Critic ────────────────────────────────────────────────────────────────────

def render_critic(data: dict, **_):
    approved = data.get("approved", False)
    comment = data.get("comment", "")

    if approved:
        st.success("✅ Approved")
    else:
        st.error("❌ Rejected")

    if comment:
        st.markdown(comment)


# ── Judge ─────────────────────────────────────────────────────────────────────

def render_judge(data: dict, extra_data: dict = None, **_):
    extra_data = extra_data or {}
    val_results = extra_data.get("validation_results") or {}
    op_report = extra_data.get("operation_report") or {}

    assessment = data.get("overall_assessment", {})
    outcome = assessment.get("mitigation_outcome", "unknown")
    summary = assessment.get("summary", "")
    kpis = assessment.get("multi_agent_kpis") or data.get("multi_agent_kpis", {})

    effectiveness = data.get("mitigation_effectiveness")
    baseline = data.get("baseline_success_rate")
    current = data.get("current_success_rate")
    is_mitigated = data.get("is_attack_mitigated")
    agent_scores = data.get("agent_scores", {})
    notes = data.get("notes", {})

    # ── Outcome ───────────────────────────────────────────────────────────
    if outcome == "success":
        st.success("✅ Outcome: **SUCCESS**")
    elif outcome == "failure":
        st.error("❌ Outcome: **FAILURE**")
    else:
        st.info(f"Outcome: {outcome}")

    # ── Attack rate regression ────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    if baseline is not None:
        c1.metric("Baseline attack rate", f"{baseline * 100:.0f}%")
    if current is not None:
        delta = None if baseline is None else f"{(current - baseline) * 100:+.0f}%"
        c2.metric("Post-mitigation rate", f"{current * 100:.0f}%", delta=delta, delta_color="inverse")
    if effectiveness is not None:
        c3.metric("Effectiveness", f"{effectiveness * 100:.0f}%")

    if summary:
        st.markdown(summary)

    # ── Attack step regression table (from operation report) ──────────────
    steps_by_paw = op_report.get("steps", {})
    all_steps = []
    for paw_data in steps_by_paw.values():
        all_steps.extend(paw_data.get("steps", []))

    if all_steps:
        st.markdown("**Attack step results after mitigation**")
        rows = []
        for step in all_steps:
            status_code = step.get("status", -1)
            if status_code == 0:
                icon, label = "✅", "Success"
            elif status_code == -3:
                icon, label = "⏭", "Skipped"
            else:
                icon, label = "❌", f"Failed ({status_code})"
            output = step.get("output", {})
            rows.append({
                "Step": step.get("name", step.get("ability_id", "?")),
                "Result": f"{icon} {label}",
                "Output": str(output.get("stdout", ""))[:120],
            })
        st.dataframe(rows, width="stretch", hide_index=True)

    # ── Validity checks (from validation_results.json) ────────────────────
    validity_checks = val_results.get("validity_checks", {})
    if validity_checks:
        st.markdown("**Validity checks**")
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
                    st.markdown("**stdout**")
                    st.code(stdout, language="text")
                if stderr:
                    st.markdown("**stderr**")
                    st.code(stderr, language="text")

    # ── KPIs ──────────────────────────────────────────────────────────────
    if kpis:
        st.markdown("**Team KPIs**")
        for kpi_key, kpi_val in kpis.items():
            if not isinstance(kpi_val, dict):
                continue
            score = kpi_val.get("score", 0)
            justification = kpi_val.get("justification", "")
            label = kpi_key.replace("_", " ").title()
            with st.expander(f"{label} — {_score_bar(score)}", expanded=False):
                st.markdown(justification)

    # ── Per-agent scores ──────────────────────────────────────────────────
    if agent_scores:
        st.markdown("**Agent scores**")
        for agent_key, criteria in agent_scores.items():
            if not isinstance(criteria, dict):
                continue
            scores = [v["score"] for v in criteria.values() if isinstance(v, dict) and "score" in v]
            avg = sum(scores) / len(scores) if scores else 0
            agent_label = agent_key.replace("_", " ").title()
            with st.expander(f"{agent_label} — avg {avg:.1f}/10", expanded=False):
                for kpi_key, kpi_val in criteria.items():
                    if not isinstance(kpi_val, dict):
                        continue
                    score = kpi_val.get("score", 0)
                    just = kpi_val.get("justification", "")
                    st.markdown(f"**{kpi_key.replace('_', ' ').title()}** — {_score_bar(score)}")
                    st.caption(just)

    # ── Notes ─────────────────────────────────────────────────────────────
    missing = notes.get("missing_information_or_uncertainty", "")
    assumptions = notes.get("assumptions_made", "")
    if missing or assumptions:
        with st.expander("Notes", expanded=False):
            if missing:
                st.markdown(f"**Missing information:** {missing}")
            if assumptions:
                st.markdown(f"**Assumptions:** {assumptions}")


# ── Single agent ──────────────────────────────────────────────────────────────

def render_single_agent(data: dict, **_):
    mitigation = data.get("mitigation_suggested", data.get("mitigation_currently_implemented", ""))
    implemented = data.get("mitigation_implemented", data.get("implementation_successful"))
    device = data.get("device_identifier", "")
    commands = data.get("commands", "")
    critique = data.get("critique", "")

    if data.get("reached_mitigation_limit"):
        st.warning("Mitigation limit reached.")
        return

    if mitigation:
        st.markdown("**Mitigation**")
        st.info(mitigation)
    if device:
        st.markdown(f"**Device:** `{device}`")
    if implemented is not None:
        if implemented:
            st.success("Implementation successful")
        else:
            st.error("Implementation failed")
    if critique:
        st.markdown("**Self-critique**")
        st.markdown(critique)
    if commands:
        with st.expander("Commands executed", expanded=False):
            st.code(str(commands), language="bash")


# ── Dispatch ──────────────────────────────────────────────────────────────────

_RENDERERS = {
    "mitigation_suggester": render_suggester,
    "mitigation_implementer": render_implementer,
    "critic": render_critic,
    "judge": render_judge,
    "single_agent": render_single_agent,
    "shieldgpt_agent": render_single_agent,
}


def render_agent_message(agent_name: str, parsed: dict, tool_calls: list = None, extra_data: dict = None):
    renderer = _RENDERERS.get(agent_name)
    if renderer:
        renderer(parsed, tool_calls=tool_calls or [], extra_data=extra_data or {})
    else:
        st.json(parsed, expanded=True)
