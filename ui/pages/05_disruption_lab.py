"""Page 5: Disruption Lab — simulate supply chain failures and demand surges."""

import streamlit as st
import pandas as pd

from core.scenario import Scenario
from models.disruption import DisruptionModel
from models.solver_utils import extract_solution, solution_to_metrics_dict
from ui.components.network_graph import plot_network
from ui.components.cost_breakdown import plot_cost_split, plot_ration_composition
from ui.components.nutrition_radar import plot_nutrition_radar
from ui.tooltips import get_tooltip_body


def render():
    st.header("Disruption Lab")
    st.markdown(get_tooltip_body("disruption"))

    if "scenario" not in st.session_state:
        st.warning("Please load a scenario first.")
        return

    scenario: Scenario = st.session_state["scenario"]

    # Disruption configuration
    st.subheader("Configure Disruptions")

    col_nodes, col_edges = st.columns(2)

    with col_nodes:
        st.markdown("**Disable Supply Nodes**")
        disabled_nodes = []
        for node in scenario.supply_nodes:
            ntype = scenario.get_node_type(node)
            if st.checkbox(f"❌ {node} ({ntype.split('_')[-1]})", key=f"dis_node_{node}"):
                disabled_nodes.append(node)

    with col_edges:
        st.markdown("**Disable Transport Routes**")
        disabled_edges = []
        # Group edges by source for cleaner display
        edge_groups = {}
        for (src, tgt) in scenario.edge_index:
            if src not in edge_groups:
                edge_groups[src] = []
            edge_groups[src].append(tgt)

        for src, targets in edge_groups.items():
            with st.expander(f"Routes from {src}", expanded=False):
                for tgt in targets:
                    cost = scenario.get_transport_cost(src, tgt)
                    if st.checkbox(
                        f"❌ {src} → {tgt} (${cost:,.0f}/MT)",
                        key=f"dis_edge_{src}_{tgt}",
                    ):
                        disabled_edges.append((src, tgt))

    # Budget option
    use_budget = st.checkbox("Apply budget constraint")
    budget = None
    if use_budget:
        budget = st.slider("Budget ($)", 1000.0, 30000.0, 6000.0, 100.0)

    # Solve
    col_solve, col_status = st.columns([1, 3])
    with col_solve:
        solve_btn = st.button("🔧 Solve Under Disruption", type="primary")

    if solve_btn:
        with st.spinner("Building and solving disrupted model..."):
            try:
                model = DisruptionModel(scenario, budget=budget)
                status = model.apply_disruptions(
                    disabled_edges=disabled_edges,
                    disabled_nodes=disabled_nodes,
                )

                if model.is_solved:
                    sol = extract_solution(model)
                    st.session_state["disruption_solution"] = sol

                    # Add to solutions library
                    if "solutions_library" not in st.session_state:
                        st.session_state["solutions_library"] = {}
                    label = f"Disrupted ({len(disabled_nodes)}N, {len(disabled_edges)}E)"
                    st.session_state["solutions_library"][label] = sol

                    st.success(f"Solved! Status: {status}")
                else:
                    st.error(
                        f"Infeasible under these disruptions (status: {status}). "
                        "The supply chain cannot meet demand with these failures."
                    )
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results
    if "disruption_solution" in st.session_state:
        sol = st.session_state["disruption_solution"]

        st.subheader("Disrupted Solution")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Cost", f"${sol.total_cost:,.0f}")
        with col2:
            st.metric("Nutrient Slack", f"{sol.nutrient_slack:.3f}")
        with col3:
            st.metric("Cost/Person", f"${sol.cost_per_person:,.2f}")
        with col4:
            st.metric("Active Routes", sol.num_active_transport)

        tab_net, tab_ration, tab_nutrition = st.tabs(["Network", "Ration", "Nutrition"])

        with tab_net:
            st.plotly_chart(
                plot_network(scenario, sol, title="Disrupted Network"),
                width="stretch",
            )

        with tab_ration:
            st.plotly_chart(
                plot_ration_composition(scenario, sol, title="Ration Under Disruption"),
                width="stretch",
            )

        with tab_nutrition:
            solutions_to_compare = {"Disrupted": sol}
            # Add baseline if available
            if "solutions_library" in st.session_state:
                for label, s in st.session_state["solutions_library"].items():
                    if "Nominal" in label:
                        solutions_to_compare["Nominal (Baseline)"] = s
                        break
            st.plotly_chart(
                plot_nutrition_radar(scenario, solutions_to_compare),
                width="stretch",
            )

        # Comparison with baseline
        if "solutions_library" in st.session_state:
            baseline_keys = [k for k in st.session_state["solutions_library"] if "Nominal" in k]
            if baseline_keys:
                baseline = st.session_state["solutions_library"][baseline_keys[0]]
                st.subheader("Impact vs. Baseline")
                col1, col2, col3 = st.columns(3)
                with col1:
                    delta_cost = sol.total_cost - baseline.total_cost
                    st.metric("Cost Change", f"${sol.total_cost:,.0f}",
                              delta=f"${delta_cost:+,.0f}", delta_color="inverse")
                with col2:
                    delta_slack = sol.nutrient_slack - baseline.nutrient_slack
                    st.metric("Slack Change", f"{sol.nutrient_slack:.3f}",
                              delta=f"{delta_slack:+.3f}")
                with col3:
                    delta_routes = sol.num_active_transport - baseline.num_active_transport
                    st.metric("Routes Change", sol.num_active_transport,
                              delta=f"{delta_routes:+d}")
