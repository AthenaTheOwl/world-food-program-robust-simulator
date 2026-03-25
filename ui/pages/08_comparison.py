"""Page 8: Head-to-Head Comparison — side-by-side scenario diff."""

import streamlit as st
import pandas as pd

from core.scenario import Scenario
from models.solver_utils import SolutionResult, solution_to_metrics_dict
from ui.components.network_graph import plot_network
from ui.components.nutrition_radar import plot_nutrition_radar
from ui.components.cost_breakdown import plot_cost_split, plot_ration_composition
from ui.components.tradeoff_curve import plot_tradeoff_curve


def render():
    st.header("Head-to-Head Comparison")

    if "scenario" not in st.session_state:
        st.warning("Please load a scenario first.")
        return

    scenario: Scenario = st.session_state["scenario"]

    if "solutions_library" not in st.session_state or len(st.session_state["solutions_library"]) < 2:
        st.info(
            "Need at least 2 solutions to compare. "
            "Go to **Optimization** and solve multiple models first."
        )
        return

    library = st.session_state["solutions_library"]
    labels = list(library.keys())

    col1, col2 = st.columns(2)
    with col1:
        label_a = st.selectbox("Solution A", labels, index=0)
    with col2:
        default_b = min(1, len(labels) - 1)
        label_b = st.selectbox("Solution B", labels, index=default_b)

    if label_a == label_b:
        st.warning("Select two different solutions to compare.")
        return

    sol_a = library[label_a]
    sol_b = library[label_b]

    # === Metrics comparison ===
    st.subheader("Metrics Comparison")

    metrics_a = solution_to_metrics_dict(sol_a)
    metrics_b = solution_to_metrics_dict(sol_b)

    # Delta indicators
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        delta_cost = sol_b.total_cost - sol_a.total_cost
        st.metric(
            "Total Cost",
            f"${sol_a.total_cost:,.0f} vs ${sol_b.total_cost:,.0f}",
            delta=f"${delta_cost:+,.0f}",
            delta_color="inverse",
        )
    with col2:
        delta_slack = sol_b.nutrient_slack - sol_a.nutrient_slack
        st.metric(
            "Nutrient Slack",
            f"{sol_a.nutrient_slack:.3f} vs {sol_b.nutrient_slack:.3f}",
            delta=f"{delta_slack:+.3f}",
        )
    with col3:
        delta_cpp = sol_b.cost_per_person - sol_a.cost_per_person
        st.metric(
            "Cost/Person",
            f"${sol_a.cost_per_person:,.2f} vs ${sol_b.cost_per_person:,.2f}",
            delta=f"${delta_cpp:+,.2f}",
            delta_color="inverse",
        )
    with col4:
        delta_intl = sol_b.international_procurement_ratio - sol_a.international_procurement_ratio
        st.metric(
            "Intl Procurement",
            f"{sol_a.international_procurement_ratio:.0%} vs {sol_b.international_procurement_ratio:.0%}",
            delta=f"{delta_intl:+.1%}",
        )

    # Full metrics table
    with st.expander("Full Metrics Table"):
        df = pd.DataFrame({label_a: metrics_a, label_b: metrics_b}).T
        st.dataframe(df, width="stretch")

    # === Side-by-side visualizations ===
    st.subheader("Visual Comparison")

    tab_network, tab_ration, tab_nutrition, tab_cost = st.tabs(
        ["Network", "Ration", "Nutrition", "Cost"]
    )

    with tab_network:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**{label_a}**")
            st.plotly_chart(
                plot_network(scenario, sol_a, title=label_a, height=450),
                width="stretch",
            )
        with col2:
            st.markdown(f"**{label_b}**")
            st.plotly_chart(
                plot_network(scenario, sol_b, title=label_b, height=450),
                width="stretch",
            )

    with tab_ration:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                plot_ration_composition(scenario, sol_a, title=f"Ration — {label_a}"),
                width="stretch",
            )
        with col2:
            st.plotly_chart(
                plot_ration_composition(scenario, sol_b, title=f"Ration — {label_b}"),
                width="stretch",
            )

        # Ration diff
        with st.expander("Ration Differences"):
            all_comms = set(sol_a.ration_pp.keys()) | set(sol_b.ration_pp.keys())
            diff_rows = []
            for c in sorted(all_comms):
                va = sol_a.ration_pp.get(c, 0)
                vb = sol_b.ration_pp.get(c, 0)
                if abs(va - vb) > 1e-4:
                    diff_rows.append({
                        "Commodity": c,
                        label_a: f"{va:.4f} kg",
                        label_b: f"{vb:.4f} kg",
                        "Change": f"{vb - va:+.4f} kg",
                    })
            if diff_rows:
                st.dataframe(pd.DataFrame(diff_rows), width="stretch")
            else:
                st.info("Rations are identical.")

    with tab_nutrition:
        st.plotly_chart(
            plot_nutrition_radar(scenario, {label_a: sol_a, label_b: sol_b}),
            width="stretch",
        )

    with tab_cost:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                plot_cost_split(sol_a, title=f"Cost — {label_a}"),
                width="stretch",
            )
        with col2:
            st.plotly_chart(
                plot_cost_split(sol_b, title=f"Cost — {label_b}"),
                width="stretch",
            )

    # === Procurement shift analysis ===
    st.subheader("Procurement Shift Analysis")

    all_proc_keys = set(sol_a.procurement.keys()) | set(sol_b.procurement.keys())
    shift_rows = []
    for (n, c) in sorted(all_proc_keys):
        va = sol_a.procurement.get((n, c), 0)
        vb = sol_b.procurement.get((n, c), 0)
        if abs(va - vb) > 0.01:
            shift_rows.append({
                "Node": n,
                "Commodity": c,
                f"{label_a} (MT)": round(va, 3),
                f"{label_b} (MT)": round(vb, 3),
                "Change (MT)": round(vb - va, 3),
            })

    if shift_rows:
        df_shifts = pd.DataFrame(shift_rows)
        st.dataframe(df_shifts, width="stretch")

        # Summary by node
        st.markdown("**Net procurement change by node:**")
        node_changes = {}
        for row in shift_rows:
            node = row["Node"]
            if node not in node_changes:
                node_changes[node] = 0
            node_changes[node] += row["Change (MT)"]

        for node, change in sorted(node_changes.items(), key=lambda x: -abs(x[1])):
            ntype = scenario.get_node_type(node)
            direction = "📈" if change > 0 else "📉"
            st.markdown(f"  {direction} **{node}** ({ntype}): {change:+.3f} MT")
    else:
        st.info("No procurement differences between the two solutions.")

    # === Value of robustness summary ===
    if sol_a.robustness_level != sol_b.robustness_level:
        st.subheader("The Value of Robustness")

        # Determine which is more robust
        if sol_a.robustness_level < sol_b.robustness_level:
            less_robust, more_robust = sol_a, sol_b
            lr_label, mr_label = label_a, label_b
        else:
            less_robust, more_robust = sol_b, sol_a
            lr_label, mr_label = label_b, label_a

        cost_increase = more_robust.total_cost - less_robust.total_cost
        pct_increase = cost_increase / less_robust.total_cost * 100 if less_robust.total_cost > 0 else 0
        protection_gain = more_robust.robustness_level - less_robust.robustness_level

        st.markdown(
            f"Moving from **{lr_label}** (p={less_robust.robustness_level:.0%}) to "
            f"**{mr_label}** (p={more_robust.robustness_level:.0%}):"
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Extra Cost", f"${cost_increase:,.0f}", delta=f"+{pct_increase:.1f}%",
                       delta_color="inverse")
        with col2:
            st.metric("Protection Gain", f"+{protection_gain:.0%}")
        with col3:
            intl_shift = more_robust.international_procurement_ratio - less_robust.international_procurement_ratio
            st.metric("Intl Procurement Shift", f"+{intl_shift:.0%}")
