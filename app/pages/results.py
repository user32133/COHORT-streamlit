import streamlit as st

from app.config import load_json, list_experiments, list_sub_runs, sorted_mitigation_dirs
from app.data_parser import collect_all_judge_scores, collect_cross_experiment_scores


def render_results_page():
    st.title("Results Dashboard")

    tab_summary, tab_scores, tab_compare = st.tabs(
        ["Experiment Summary", "Judge Scores", "Cross-Run Comparison"]
    )

    experiments = list_experiments()

    # ── TAB 1: Experiment Summary ─────────────────────────────────────────────
    with tab_summary:
        if not experiments:
            st.info("No experiments found.")
        else:
            last = st.session_state.get("last_experiment_dir")
            exp_options = {e.name: e for e in experiments}
            default_exp = last.name if last and last.name in exp_options else list(exp_options.keys())[0]

            chosen_exp_name = st.selectbox(
                "Experiment",
                options=list(exp_options.keys()),
                index=list(exp_options.keys()).index(default_exp),
                key="sum_exp",
            )
            exp_dir = exp_options[chosen_exp_name]

            # Config
            config = load_json(exp_dir / "config.json")
            if config:
                with st.expander("Run Configuration", expanded=False):
                    st.json(config)

            # Sub-run selector
            sub_runs = list_sub_runs(exp_dir)
            if not sub_runs:
                st.info("No sub-runs found.")
            else:
                sub_run_options = {s.name: s for s in sub_runs}
                chosen_sub = st.selectbox("Sub-run", options=list(sub_run_options.keys()), key="sum_sub")
                sub_run_dir = sub_run_options[chosen_sub]

                summary = load_json(sub_run_dir / "summary.json")
                if summary:
                    st.subheader("Attack Summary")
                    st.info(summary.get("attack_summary", ""))

                    mitigations = summary.get("mitigations", [])
                    if mitigations:
                        st.subheader("Mitigations")
                        for mit in mitigations:
                            outcome = mit.get("outcome", "unknown")
                            color = "green" if outcome == "success" else "red"
                            num = mit.get("number", mit.get("mitigation_number", "?"))
                            name = mit.get("name", mit.get("mitigation_name", "Mitigation"))
                            with st.expander(f"Mitigation {num}: {name} — :{color}[{outcome.upper()}]"):
                                st.markdown(mit.get("brief_description", mit.get("description", "")))
                else:
                    st.info("No summary.json found for this sub-run. Run may still be in progress.")

                # Quick score table from judge evaluations
                scores = collect_all_judge_scores(sub_run_dir)
                if scores:
                    st.subheader("Mitigation Scores")
                    st.dataframe(scores, width="stretch", hide_index=True)

    # ── TAB 2: Judge Scores ───────────────────────────────────────────────────
    with tab_scores:
        if not experiments:
            st.info("No experiments found.")
        else:
            exp_options2 = {e.name: e for e in experiments}
            last2 = st.session_state.get("last_experiment_dir")
            default_exp2 = last2.name if last2 and last2.name in exp_options2 else list(exp_options2.keys())[0]

            chosen_exp2 = st.selectbox(
                "Experiment",
                options=list(exp_options2.keys()),
                index=list(exp_options2.keys()).index(default_exp2),
                key="score_exp",
            )
            exp_dir2 = exp_options2[chosen_exp2]

            sub_runs2 = list_sub_runs(exp_dir2)
            if not sub_runs2:
                st.info("No sub-runs found.")
            else:
                sub_run_options2 = {s.name: s for s in sub_runs2}
                chosen_sub2 = st.selectbox("Sub-run", options=list(sub_run_options2.keys()), key="score_sub")
                sub_run_dir2 = sub_run_options2[chosen_sub2]

                single_dir2 = sub_run_dir2 / "single"
                if not single_dir2.exists():
                    single_dir2 = sub_run_dir2
                mit_dirs2 = sorted_mitigation_dirs(single_dir2)

                if not mit_dirs2:
                    st.info("No mitigation data found.")
                else:
                    mit_options2 = {m.name: m for m in mit_dirs2}
                    chosen_mit2 = st.selectbox(
                        "Mitigation",
                        options=list(mit_options2.keys()),
                        format_func=lambda n: n.replace("_", " ").title(),
                        key="score_mit",
                    )
                    mit_dir2 = mit_options2[chosen_mit2]

                    eval_data = load_json(mit_dir2 / "judge_evaluation.json")
                    val_data = load_json(mit_dir2 / "validation_results.json")

                    if not eval_data:
                        st.info("No judge_evaluation.json found for this mitigation.")
                    else:
                        # Top metrics
                        assessment = eval_data.get("overall_assessment", {})
                        outcome = assessment.get("mitigation_outcome", "unknown")


                        c1, c2, c3, c4, c5 = st.columns(5)
                        c1.metric("Outcome", outcome.upper())
                        c2.metric(
                            "Effectiveness",
                            f"{eval_data.get('mitigation_effectiveness', 0) * 100:.0f}%",
                        )
                        c3.metric(
                            "Baseline Rate",
                            f"{eval_data.get('baseline_success_rate', 0) * 100:.0f}%",
                        )
                        c4.metric(
                            "Current Rate",
                            f"{eval_data.get('current_success_rate', 0) * 100:.0f}%",
                        )
                        c5.metric("Category", eval_data.get("mitigation_category", "N/A"))

                        summary_text = assessment.get("summary", "")
                        if summary_text:
                            st.caption(summary_text)

                        # Multi-agent KPIs bar chart
                        kpis = eval_data.get("multi_agent_kpis", {})
                        if kpis:
                            st.subheader("Team KPIs")
                            kpi_data = {}
                            for k, v in kpis.items():
                                if isinstance(v, dict) and "score" in v:
                                    kpi_data[k.replace("_", " ").title()] = v["score"]
                            if kpi_data:
                                st.bar_chart(kpi_data)
                            # KPI justifications
                            for k, v in kpis.items():
                                if isinstance(v, dict):
                                    with st.expander(k.replace("_", " ").title()):
                                        st.write(f"**Score:** {v.get('score', 'N/A')}/10")
                                        st.write(v.get("justification", ""))

                        # Per-agent scores
                        agent_scores = eval_data.get("agent_scores", {})
                        if agent_scores:
                            st.subheader("Agent Score Breakdown")

                            # Summary bar per agent
                            agent_avgs = {}
                            for agent, criteria in agent_scores.items():
                                scores = [v["score"] for v in criteria.values() if isinstance(v, dict) and "score" in v]
                                agent_avgs[agent.replace("_", " ").title()] = (
                                    sum(scores) / len(scores) if scores else 0
                                )
                            if agent_avgs:
                                st.bar_chart(agent_avgs)

                            for agent, criteria in agent_scores.items():
                                scores_list = [v["score"] for v in criteria.values() if isinstance(v, dict) and "score" in v]
                                avg = sum(scores_list) / len(scores_list) if scores_list else 0
                                with st.expander(f"{agent.replace('_', ' ').title()} — avg {avg:.1f}/10"):
                                    rows = []
                                    for kpi_name, kpi_data in criteria.items():
                                        if isinstance(kpi_data, dict):
                                            rows.append({
                                                "KPI": kpi_name.replace("_", " ").title(),
                                                "Score": kpi_data.get("score", ""),
                                                "Justification": kpi_data.get("justification", ""),
                                            })
                                    if rows:
                                        st.dataframe(rows, width="stretch", hide_index=True)

                    # Validation results
                    if val_data:
                        st.subheader("Validation Results")
                        vc1, vc2, vc3 = st.columns(3)
                        vc1.metric(
                            "Mitigated",
                            "Yes" if val_data.get("is_attack_mitigated") else "No",
                        )
                        vc2.metric(
                            "Effectiveness",
                            f"{val_data.get('mitigation_effectiveness', 0) * 100:.0f}%",
                        )
                        vc3.metric("Success", "Yes" if val_data.get("success") else "No")

                        validity_checks = val_data.get("validity_checks", {})
                        if validity_checks:
                            for check_name, check_data in validity_checks.items():
                                if not isinstance(check_data, dict):
                                    continue
                                ok = check_data.get("success", False)
                                icon = "✅" if ok else "❌"
                                with st.expander(f"{icon} {check_name}"):
                                    stdout = check_data.get("stdout", "")
                                    if stdout:
                                        st.code(str(stdout)[:1000], language="text")
                                    st.json({k: v for k, v in check_data.items() if k != "stdout"}, expanded=False)

    # ── TAB 3: Cross-Run Comparison ───────────────────────────────────────────
    with tab_compare:
        st.subheader("Aggregate Results Across Experiments")

        if not experiments:
            st.info("No experiments found.")
        else:
            with st.spinner("Aggregating scores..."):
                rows = collect_cross_experiment_scores(experiments[:20])  # cap at 20 for performance

            if not rows:
                st.info("No judge evaluation data found across experiments.")
            else:
                # Summary metrics
                total_mit = sum(r["mitigations"] for r in rows)
                total_success = sum(r["successes"] for r in rows)
                overall_rate = f"{total_success / total_mit * 100:.0f}%" if total_mit else "N/A"

                sm1, sm2, sm3 = st.columns(3)
                sm1.metric("Total Mitigations", total_mit)
                sm2.metric("Total Successes", total_success)
                sm3.metric("Overall Success Rate", overall_rate)

                st.dataframe(rows, width="stretch", hide_index=True)
