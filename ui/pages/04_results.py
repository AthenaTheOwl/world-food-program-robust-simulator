"""Page 4: Results Dashboard — inspect any solved plan."""

import streamlit as st
import pandas as pd

from core.scenario import Scenario
from models.solver_utils import SolutionResult, solution_to_metrics_dict
from ui.components.shared import solution_summary_ribbon, nutrition_bars, what_changed
from ui.components.network_graph import plot_network
from ui.components.sankey import plot_sankey
from ui.components.nutrition_radar import plot_nutrition_radar
from ui.components.cost_breakdown import (
    plot_cost_split,
    plot_procurement_by_node,
    plot_ration_composition,
)
from ui.components.ops_brief import generate_ops_brief
from ui.theme import format_currency


def render():
    st.header("Results Dashboard")
    st.caption("Pick a solved plan and inspect every detail.")

    if "scenario" not in st.session_state:
        st.warning("Load a scenario first from **Scenario Manager**.")
        return

    scenario: Scenario = st.session_state["scenario"]
    library = st.session_state.get("solutions_library", {})

    if not library:
        st.info("No solutions yet. Solve a model on the **Optimize** page or visit the **Guided Overview**.")
        return

    selected_label = st.selectbox("Select plan", list(library.keys()))
    solution = library[selected_label]

    if not solution.is_optimal:
        st.error(f"Solution status: {solution.status}")
        return

    # ── Sticky summary ribbon ──
    solution_summary_ribbon(scenario, solution, label=selected_label)

    # ── Operations Brief export ──
    baseline = library.get("Nominal")
    brief_md = generate_ops_brief(scenario, solution, selected_label, sol_baseline=baseline)
    st.download_button(
        "Download Operations Brief",
        data=brief_md,
        file_name=f"ops_brief_{selected_label.replace(' ', '_').lower()}.md",
        mime="text/markdown",
    )

    # ── Nutrition at a glance ──
    col_nutr, col_charts = st.columns([1, 2])

    with col_nutr:
        st.markdown("**Nutrition check**")
        nutrition_bars(scenario, solution, compact=True)

    with col_charts:
        tab_net, tab_flow, tab_cost = st.tabs(["Network", "Flow", "Cost"])

        with tab_net:
            st.plotly_chart(
                plot_network(scenario, solution, title=f"{selected_label}"),
                width="stretch",
            )

        with tab_flow:
            st.plotly_chart(
                plot_sankey(scenario, solution, title=f"{selected_label}"),
                width="stretch",
            )

        with tab_cost:
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(plot_cost_split(solution), width="stretch")
            with c2:
                st.plotly_chart(plot_procurement_by_node(scenario, solution), width="stretch")

    # ── Ration detail (in expander) ──
    with st.expander("Show ration and nutrient details"):
        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(plot_ration_composition(scenario, solution), width="stretch")
            if solution.ration_pp:
                total_kg = sum(solution.ration_pp.values())
                st.caption(f"Total: {total_kg:.3f} kg/person/day")
        with c2:
            rows = []
            for nutrient in scenario.nutrient_list:
                req = scenario.get_requirement(nutrient)
                actual = solution.nutrients_pp.get(nutrient, 0)
                pct = (actual / req * 100) if req > 0 else 0
                rows.append({
                    "Nutrient": nutrient.split("(")[0].strip(),
                    "Requirement": f"{req:.2f}",
                    "Delivered": f"{actual:.2f}",
                    "Met": f"{pct:.0f}%",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ── Compare (if multiple solutions) ──
    if len(library) >= 2:
        st.markdown("---")
        st.markdown("### Compare plans")

        compare_labels = st.multiselect(
            "Select plans",
            list(library.keys()),
            default=list(library.keys())[:2],
            max_selections=4,
        )

        if len(compare_labels) >= 2:
            compare_sols = {lbl: library[lbl] for lbl in compare_labels}

            # Side-by-side nutrition bars
            cols = st.columns(len(compare_labels))
            for i, (lbl, sol) in enumerate(compare_sols.items()):
                with cols[i]:
                    st.markdown(f"**{lbl}**")
                    st.metric("Cost", format_currency(sol.total_cost))
                    nutrition_bars(scenario, sol, compact=True)

            with st.expander("Show detailed comparison table"):
                rows = {lbl: solution_to_metrics_dict(sol) for lbl, sol in compare_sols.items()}
                st.dataframe(pd.DataFrame(rows).T, width="stretch")
