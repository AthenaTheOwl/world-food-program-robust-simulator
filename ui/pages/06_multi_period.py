"""Page 6: Multi-Period Planner — inventory, spoilage, demand trajectories."""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

from core.scenario import Scenario
from models.multi_period import MultiPeriodModel
from ui.tooltips import get_tooltip_body


def render():
    st.header("Multi-Period Planner")
    st.markdown(get_tooltip_body("multi_period"))

    if "scenario" not in st.session_state:
        st.warning("Please load a scenario first.")
        return

    scenario: Scenario = st.session_state["scenario"]

    # Configuration
    col1, col2, col3 = st.columns(3)
    with col1:
        num_periods = st.slider("Number of periods (days)", 2, 14, 5)
    with col2:
        holding_cost = st.slider("Holding cost ($/MT/day)", 0.0, 100.0, 10.0, 5.0,
                                  help="Cost of storing one metric ton for one day")
    with col3:
        demand_pattern = st.selectbox(
            "Demand trajectory",
            ["Constant", "Linear growth", "Surge in middle", "Gradual decline", "Custom"],
        )

    # Build demand trajectory
    demand_base = np.array([scenario.demand_dict.get(d, 0) for d in scenario.demand_nodes])
    trajectory = np.tile(demand_base, (num_periods, 1))

    if demand_pattern == "Linear growth":
        for t in range(num_periods):
            trajectory[t] *= 1 + 0.1 * t  # 10% growth per period
    elif demand_pattern == "Surge in middle":
        mid = num_periods // 2
        trajectory[mid] *= 2.0  # double demand in middle period
        if mid > 0:
            trajectory[mid - 1] *= 1.3
        if mid < num_periods - 1:
            trajectory[mid + 1] *= 1.3
    elif demand_pattern == "Gradual decline":
        for t in range(num_periods):
            trajectory[t] *= max(0.3, 1 - 0.15 * t)
    elif demand_pattern == "Custom":
        st.markdown("**Custom demand multipliers per period:**")
        multipliers = []
        cols = st.columns(min(num_periods, 7))
        for t in range(num_periods):
            with cols[t % len(cols)]:
                mult = st.number_input(
                    f"Period {t+1}", 0.1, 5.0, 1.0, 0.1,
                    key=f"demand_mult_{t}",
                )
                multipliers.append(mult)
        for t in range(num_periods):
            trajectory[t] *= multipliers[t]

    # Show demand trajectory chart
    total_demand_per_period = trajectory.sum(axis=1)
    fig_demand = go.Figure()
    fig_demand.add_trace(go.Bar(
        x=list(range(1, num_periods + 1)),
        y=total_demand_per_period,
        name="Total Demand",
        marker_color="#1976D2",
        text=[f"{d:,.0f}" for d in total_demand_per_period],
        textposition="auto",
    ))
    fig_demand.update_layout(
        title="Demand Trajectory (people per period)",
        xaxis_title="Period", yaxis_title="People",
        height=300,
    )
    st.plotly_chart(fig_demand, width="stretch")

    # Spoilage info
    with st.expander("Commodity Shelf Life & Spoilage"):
        spoilage_rows = []
        for _, row in scenario.commodities.iterrows():
            cid = row["commodity_id"]
            shelf = row.get("shelf_life_days", np.inf)
            rate = (1 - np.exp(-1.0 / shelf)) * 100 if np.isfinite(shelf) and shelf > 0 else 0
            spoilage_rows.append({
                "Commodity": cid,
                "Shelf Life (days)": f"{shelf:.0f}" if np.isfinite(shelf) else "∞",
                "Daily Spoilage Rate": f"{rate:.1f}%",
            })
        st.dataframe(pd.DataFrame(spoilage_rows), width="stretch")
        st.caption(
            "Spoilage is modeled as exponential decay: rate = 1 - e^(-1/shelf_life). "
            "Commodities with infinite shelf life have 0% spoilage."
        )

    # Solve
    if st.button("🔧 Solve Multi-Period Plan", type="primary", width="stretch"):
        with st.spinner(f"Solving {num_periods}-period model..."):
            try:
                model = MultiPeriodModel(
                    scenario,
                    num_periods=num_periods,
                    demand_trajectory=trajectory,
                    holding_cost_per_ton=holding_cost,
                )
                status = model.solve()

                if model.is_solved:
                    results = model.extract_period_results()
                    st.session_state["multi_period_results"] = results
                    st.session_state["multi_period_value"] = model.problem.value
                    st.success(f"Solved! Total cost across all periods: ${model.problem.value:,.0f}")
                else:
                    st.error(f"Solver returned: {status}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results
    if "multi_period_results" in st.session_state:
        results = st.session_state["multi_period_results"]
        total_value = st.session_state.get("multi_period_value", 0)

        st.subheader("Results")
        st.metric("Total Cost (all periods)", f"${total_value:,.0f}")

        # Results table
        df = pd.DataFrame(results)
        st.dataframe(df, width="stretch")

        # Timeline charts
        periods = [r["period"] for r in results]

        tab_cost, tab_delivery, tab_inventory = st.tabs(["Cost", "Delivery", "Inventory"])

        with tab_cost:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=periods,
                y=[r["procurement_cost"] for r in results],
                name="Procurement",
                marker_color="#1976D2",
            ))
            fig.add_trace(go.Bar(
                x=periods,
                y=[r["transportation_cost"] for r in results],
                name="Transportation",
                marker_color="#FF9800",
            ))
            fig.update_layout(
                title="Cost per Period",
                barmode="stack",
                xaxis_title="Period",
                yaxis_title="Cost ($)",
                height=400,
            )
            st.plotly_chart(fig, width="stretch")

        with tab_delivery:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=periods,
                y=[r["total_delivery_tons"] for r in results],
                name="Delivery",
                marker_color="#4CAF50",
            ))
            fig.add_trace(go.Scatter(
                x=periods,
                y=[r["demand"] for r in results],
                name="Demand (people)",
                yaxis="y2",
                line=dict(color="#F44336", width=2),
                mode="lines+markers",
            ))
            fig.update_layout(
                title="Delivery vs Demand",
                xaxis_title="Period",
                yaxis_title="Delivery (MT)",
                yaxis2=dict(title="Demand (people)", overlaying="y", side="right"),
                height=400,
            )
            st.plotly_chart(fig, width="stretch")

        with tab_inventory:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=periods,
                y=[r["total_inventory_tons"] for r in results],
                mode="lines+markers",
                name="Total Inventory",
                fill="tozeroy",
                line=dict(color="#9C27B0"),
            ))
            fig.update_layout(
                title="Inventory Levels Over Time",
                xaxis_title="Period",
                yaxis_title="Inventory (MT)",
                height=400,
            )
            st.plotly_chart(fig, width="stretch")
