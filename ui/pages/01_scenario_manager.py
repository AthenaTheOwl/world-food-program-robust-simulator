"""Page 1: Scenario Manager — load, browse, and select scenarios."""

import os
import streamlit as st
from pathlib import Path

from core.scenario import Scenario
from ui.tooltips import get_tooltip
from ui.components.network_graph import plot_network
from config import APP_TITLE


def get_example_scenarios():
    """Find all bundled example scenarios."""
    examples_dir = Path(__file__).parent.parent.parent / "data" / "examples"
    scenarios = {}
    if examples_dir.exists():
        for d in examples_dir.iterdir():
            if d.is_dir() and (d / "scenario.json").exists():
                scenarios[d.name] = str(d)
    return scenarios


def render():
    st.header("Scenario Manager")
    st.markdown(
        "Select a bundled example scenario or upload your own. "
        "A scenario defines the supply network, commodities, nutritional "
        "requirements, and cost data for a food relief operation."
    )

    tab_examples, tab_upload = st.tabs(["Examples", "Upload Custom"])

    with tab_examples:
        examples = get_example_scenarios()
        if not examples:
            st.warning("No example scenarios found.")
            return

        selected = st.selectbox(
            "Select a scenario",
            options=list(examples.keys()),
            format_func=lambda x: x.replace("_", " ").title(),
        )

        if selected:
            scenario_path = examples[selected]
            try:
                scenario = Scenario.load(scenario_path)
                st.session_state["scenario"] = scenario
                st.session_state["scenario_name"] = scenario.name

                # Summary cards
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("People to Feed", f"{scenario.total_demand:,.0f}")
                with col2:
                    st.metric("Commodities", len(scenario.commodity_list))
                with col3:
                    st.metric("Supply Nodes", len(scenario.supply_nodes))
                with col4:
                    st.metric("Transport Routes", len(scenario.edge_index))

                st.markdown(f"**{scenario.name}**")
                st.markdown(scenario.description)

                # Network preview
                with st.expander("Network Preview", expanded=True):
                    fig = plot_network(scenario, title=f"{scenario.name} — Supply Network")
                    st.plotly_chart(fig, width="stretch")

                # Data tables
                with st.expander("Node Details"):
                    st.dataframe(scenario.nodes, width="stretch")

                with st.expander("Transport Routes"):
                    st.dataframe(scenario.edges, width="stretch")

                with st.expander("Commodities"):
                    st.dataframe(scenario.commodities, width="stretch")

                st.success(f"Scenario '{scenario.name}' loaded. Go to **Optimization** to solve.")

            except Exception as e:
                st.error(f"Error loading scenario: {e}")

    with tab_upload:
        st.markdown(
            "Upload a zip file or individual CSVs matching the scenario schema. "
            "Required files: `scenario.json`, `nodes.csv`, `edges.csv`, "
            "`commodities.csv`, `nutrition.csv`, `procurement_costs.csv`, "
            "`nutrition_requirements.csv`"
        )

        uploaded_files = st.file_uploader(
            "Upload scenario files",
            type=["csv", "json"],
            accept_multiple_files=True,
        )

        if uploaded_files:
            import tempfile
            import json

            with tempfile.TemporaryDirectory() as tmpdir:
                for f in uploaded_files:
                    filepath = os.path.join(tmpdir, f.name)
                    with open(filepath, "wb") as out:
                        out.write(f.getbuffer())

                try:
                    scenario = Scenario.load(tmpdir)
                    st.session_state["scenario"] = scenario
                    st.session_state["scenario_name"] = scenario.name
                    st.success(f"Custom scenario '{scenario.name}' loaded successfully!")

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("People to Feed", f"{scenario.total_demand:,.0f}")
                    with col2:
                        st.metric("Commodities", len(scenario.commodity_list))
                    with col3:
                        st.metric("Supply Nodes", len(scenario.supply_nodes))
                    with col4:
                        st.metric("Transport Routes", len(scenario.edge_index))
                except Exception as e:
                    st.error(f"Error loading scenario: {e}")

    # Tooltip
    with st.expander("ℹ️ About Scenarios"):
        st.markdown(get_tooltip("node_type"))
