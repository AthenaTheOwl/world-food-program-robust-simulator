"""Page 7: Monte Carlo — stress-test any plan against random price shocks."""

import streamlit as st
import pandas as pd

from core.scenario import Scenario
from simulation.monte_carlo import (
    generate_price_scenarios,
    evaluate_solution,
    compute_simulation_stats,
)
from ui.components.monte_carlo_viz import (
    plot_cost_histogram,
    plot_feasibility_curve,
    plot_empirical_cdf,
)
from ui.components.shared import what_changed, solution_summary_ribbon
from ui.theme import format_currency


def render():
    st.header("Monte Carlo Stress Test")
    st.caption(
        "Pick one or more plans, throw thousands of random price shocks at them, "
        "and see how often each plan stays on budget."
    )

    if "scenario" not in st.session_state:
        st.warning("Load a scenario first.")
        return

    scenario: Scenario = st.session_state["scenario"]
    library = st.session_state.get("solutions_library", {})

    if not library:
        st.info("No solutions yet. Solve a model first.")
        return

    # ── Config ──
    col1, col2, col3 = st.columns(3)
    with col1:
        selected = st.multiselect(
            "Plans to test",
            list(library.keys()),
            default=list(library.keys())[:min(3, len(library))],
        )
    with col2:
        n_scenarios = st.slider("Scenarios", 500, 10000, 2000, 500)
    with col3:
        budget_mode = st.radio(
            "Budget benchmark",
            ["Each plan's own cost", "Custom threshold"],
            help="'Own cost' checks if realized cost ≤ planned cost. "
                 "'Custom' uses a shared budget.",
        )

    custom_budget = None
    if budget_mode == "Custom threshold":
        custom_budget = st.number_input("Budget ($)", 5000.0, 100000.0, 40000.0, 1000.0)

    seed = st.number_input("Random seed", value=42, step=1)

    if st.button("Run Simulation", type="primary", use_container_width=True):
        if not selected:
            st.warning("Select at least one plan.")
            return

        with st.spinner(f"Simulating {n_scenarios:,} scenarios..."):
            prices = generate_price_scenarios(scenario, n_scenarios, int(seed))

            sim_results = {}
            stats_list = []
            for label in selected:
                sol = library[label]
                budget = custom_budget if custom_budget else sol.total_cost
                res = evaluate_solution(scenario, sol, prices, budget=budget)
                stats = compute_simulation_stats(res)
                stats["label"] = label
                stats["planned_cost"] = sol.total_cost
                stats["budget_used"] = budget
                sim_results[label] = res
                stats_list.append(stats)

            st.session_state["mc_results"] = sim_results
            st.session_state["mc_stats"] = stats_list

    # ── Results ──
    if "mc_results" not in st.session_state:
        return

    sim_results = st.session_state["mc_results"]
    stats_list = st.session_state["mc_stats"]

    # ── Punchline: survival rates ──
    st.markdown("### Results")
    cols = st.columns(len(stats_list))
    for i, s in enumerate(stats_list):
        rate = s.get("feasibility_rate", 0)
        with cols[i]:
            st.metric(
                s["label"],
                f"{rate:.0%} survive",
                delta=f"budget: {format_currency(s['budget_used'])}",
                delta_color="off",
            )

    # ── Charts ──
    col1, col2 = st.columns(2)
    budget_line = custom_budget
    with col1:
        st.plotly_chart(
            plot_cost_histogram(sim_results, budget=budget_line, title="Cost Distribution"),
            width="stretch",
        )
    with col2:
        st.plotly_chart(
            plot_empirical_cdf(sim_results, budget=budget_line, title="Cumulative Probability"),
            width="stretch",
        )

    # ── What changed ──
    lines = []
    for s in stats_list:
        rate = s.get("feasibility_rate", 0)
        lines.append(
            f"**{s['label']}**: {rate:.0%} of scenarios stay within "
            f"{format_currency(s['budget_used'])} (mean realized: {format_currency(s['mean_cost'])})"
        )
    what_changed(lines)

    # ── Detail table in expander ──
    with st.expander("Show detailed statistics"):
        rows = []
        for s in stats_list:
            rows.append({
                "Plan": s["label"],
                "Planned": format_currency(s["planned_cost"]),
                "Budget": format_currency(s["budget_used"]),
                "Mean": format_currency(s["mean_cost"]),
                "Std Dev": format_currency(s["std_cost"]),
                "Survives": f"{s.get('feasibility_rate', 0):.1%}",
                "95th Pct": format_currency(s["p95_cost"]),
                "99th Pct": format_currency(s["p99_cost"]),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.expander("Calibration: theoretical vs empirical"):
        feasibility_data = [
            {
                "robustness_level": library[s["label"]].robustness_level,
                "empirical_feasibility": s.get("feasibility_rate", 0.5),
            }
            for s in stats_list
            if s["label"] in library
        ]
        if feasibility_data:
            st.plotly_chart(plot_feasibility_curve(feasibility_data), width="stretch")
            st.caption("Points near the diagonal = well-calibrated. Above = more robust than predicted.")
