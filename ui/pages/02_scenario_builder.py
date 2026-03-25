"""Page 2: Visual Scenario Builder — construct scenarios interactively."""

import json
import io
import zipfile

import streamlit as st
import pandas as pd
import numpy as np

from core.scenario import Scenario
from config import VALID_NODE_TYPES, NODE_TYPE_LABELS


def render():
    st.header("Scenario Builder")
    st.markdown(
        "Build a custom food relief scenario interactively. "
        "Define nodes, transportation routes, commodities, and nutritional data."
    )

    # Initialize builder state
    if "builder_nodes" not in st.session_state:
        _init_builder_state()

    tab_nodes, tab_edges, tab_commodities, tab_costs, tab_nutrition, tab_export = st.tabs(
        ["Nodes", "Routes", "Commodities", "Procurement Costs", "Nutrition", "Export"]
    )

    with tab_nodes:
        _render_nodes_editor()

    with tab_edges:
        _render_edges_editor()

    with tab_commodities:
        _render_commodities_editor()

    with tab_costs:
        _render_costs_editor()

    with tab_nutrition:
        _render_nutrition_editor()

    with tab_export:
        _render_export()


def _init_builder_state():
    """Initialize empty builder state."""
    st.session_state.builder_nodes = pd.DataFrame({
        "node_id": pd.Series(dtype="str"),
        "node_type": pd.Series(dtype="str"),
        "demand_persons": pd.Series(dtype="float"),
        "latitude": pd.Series(dtype="float"),
        "longitude": pd.Series(dtype="float"),
        "country": pd.Series(dtype="str"),
    })
    st.session_state.builder_edges = pd.DataFrame({
        "source": pd.Series(dtype="str"),
        "target": pd.Series(dtype="str"),
        "transport_cost_per_ton": pd.Series(dtype="float"),
    })
    st.session_state.builder_commodities = pd.DataFrame({
        "commodity_id": pd.Series(dtype="str"),
        "category": pd.Series(dtype="str"),
        "shelf_life_days": pd.Series(dtype="float"),
    })
    st.session_state.builder_costs = pd.DataFrame({
        "node_id": pd.Series(dtype="str"),
        "commodity_id": pd.Series(dtype="str"),
        "price_per_ton": pd.Series(dtype="float"),
        "price_std_fraction": pd.Series(dtype="float"),
        "correlation_group": pd.Series(dtype="str"),
        "cross_correlation": pd.Series(dtype="float"),
    })
    st.session_state.builder_nutrition = pd.DataFrame({
        "commodity_id": pd.Series(dtype="str"),
        "nutrient_name": pd.Series(dtype="str"),
        "per_100g": pd.Series(dtype="float"),
    })
    st.session_state.builder_requirements = pd.DataFrame({
        "nutrient_name": pd.Series(dtype="str"),
        "min_per_person_day": pd.Series(dtype="float"),
    })
    st.session_state.builder_meta = {
        "name": "New Scenario",
        "description": "",
        "currency": "USD",
    }


def _render_nodes_editor():
    st.subheader("Supply Chain Nodes")

    # Quick-add form
    with st.expander("Add Node", expanded=len(st.session_state.builder_nodes) == 0):
        col1, col2 = st.columns(2)
        with col1:
            new_id = st.text_input("Node ID", placeholder="e.g. Istanbul")
            new_type = st.selectbox("Type", list(VALID_NODE_TYPES),
                                     format_func=lambda x: NODE_TYPE_LABELS.get(x, x))
        with col2:
            new_lat = st.number_input("Latitude", -90.0, 90.0, 0.0, format="%.4f")
            new_lon = st.number_input("Longitude", -180.0, 180.0, 0.0, format="%.4f")
        new_demand = st.number_input("Demand (people)", 0, 1000000, 0)
        new_country = st.text_input("Country", "")

        if st.button("Add Node"):
            if new_id:
                new_row = pd.DataFrame([{
                    "node_id": new_id,
                    "node_type": new_type,
                    "demand_persons": float(new_demand) if new_demand > 0 else np.nan,
                    "latitude": new_lat,
                    "longitude": new_lon,
                    "country": new_country,
                }])
                st.session_state.builder_nodes = pd.concat(
                    [st.session_state.builder_nodes, new_row], ignore_index=True
                )
                st.rerun()

    # Editable table
    if not st.session_state.builder_nodes.empty:
        st.markdown(f"**{len(st.session_state.builder_nodes)} nodes defined**")
        edited = st.data_editor(
            st.session_state.builder_nodes,
            width="stretch",
            num_rows="dynamic",
            column_config={
                "node_type": st.column_config.SelectboxColumn(
                    "Type", options=list(VALID_NODE_TYPES), required=True
                ),
            },
        )
        st.session_state.builder_nodes = edited

        # Map preview
        map_data = st.session_state.builder_nodes.dropna(subset=["latitude", "longitude"])
        if not map_data.empty and map_data["latitude"].abs().max() > 0.01:
            st.map(map_data, latitude="latitude", longitude="longitude")


def _render_edges_editor():
    st.subheader("Transportation Routes")

    node_ids = st.session_state.builder_nodes["node_id"].tolist() if not st.session_state.builder_nodes.empty else []

    if not node_ids:
        st.info("Add nodes first to define routes.")
        return

    with st.expander("Add Route"):
        col1, col2, col3 = st.columns(3)
        with col1:
            src = st.selectbox("Source", node_ids, key="edge_src")
        with col2:
            tgt = st.selectbox("Target", node_ids, key="edge_tgt")
        with col3:
            cost = st.number_input("Cost ($/MT)", 0.0, 10000.0, 500.0)

        if st.button("Add Route"):
            new_row = pd.DataFrame([{
                "source": src, "target": tgt, "transport_cost_per_ton": cost
            }])
            st.session_state.builder_edges = pd.concat(
                [st.session_state.builder_edges, new_row], ignore_index=True
            )
            st.rerun()

    if not st.session_state.builder_edges.empty:
        st.markdown(f"**{len(st.session_state.builder_edges)} routes defined**")
        edited = st.data_editor(
            st.session_state.builder_edges,
            width="stretch",
            num_rows="dynamic",
        )
        st.session_state.builder_edges = edited


def _render_commodities_editor():
    st.subheader("Food Commodities")

    categories = ["grain", "legume", "protein", "dairy", "fortified", "fat", "sweetener", "condiment", "other"]

    # Template loader
    if st.button("Load common commodities template"):
        template = pd.DataFrame([
            {"commodity_id": "Rice", "category": "grain", "shelf_life_days": 365},
            {"commodity_id": "Wheat flour", "category": "grain", "shelf_life_days": 180},
            {"commodity_id": "Beans", "category": "legume", "shelf_life_days": 365},
            {"commodity_id": "Lentils", "category": "legume", "shelf_life_days": 365},
            {"commodity_id": "Oil", "category": "fat", "shelf_life_days": 365},
            {"commodity_id": "Sugar", "category": "sweetener", "shelf_life_days": 730},
            {"commodity_id": "Salt", "category": "condiment", "shelf_life_days": np.inf},
            {"commodity_id": "Milk (powdered)", "category": "dairy", "shelf_life_days": 365},
        ])
        st.session_state.builder_commodities = template
        st.rerun()

    edited = st.data_editor(
        st.session_state.builder_commodities,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "category": st.column_config.SelectboxColumn("Category", options=categories),
        },
    )
    st.session_state.builder_commodities = edited


def _render_costs_editor():
    st.subheader("Procurement Costs")
    st.caption("Define prices for each commodity at each supplier node.")

    node_ids = st.session_state.builder_nodes["node_id"].tolist()
    commodity_ids = st.session_state.builder_commodities["commodity_id"].tolist()

    if not node_ids or not commodity_ids:
        st.info("Add nodes and commodities first.")
        return

    edited = st.data_editor(
        st.session_state.builder_costs,
        width="stretch",
        num_rows="dynamic",
        column_config={
            "node_id": st.column_config.SelectboxColumn("Supplier", options=node_ids),
            "commodity_id": st.column_config.SelectboxColumn("Commodity", options=commodity_ids),
        },
    )
    st.session_state.builder_costs = edited


def _render_nutrition_editor():
    st.subheader("Nutritional Data")

    standard_nutrients = [
        "Energy(kcal)", "Protein(g)", "Fat(g)", "Calcium(mg)", "Iron(mg)",
        "VitaminA(ug)", "ThiamineB1(mg)", "RiboflavinB2(mg)", "NicacinB3(mg)",
        "Folate(ug)", "VitaminC(mg)", "Iodine(ug)",
    ]

    tab_content, tab_req = st.tabs(["Nutrient Content", "Requirements"])

    with tab_content:
        st.caption("Nutrient content per 100g of each commodity.")
        edited = st.data_editor(
            st.session_state.builder_nutrition,
            width="stretch",
            num_rows="dynamic",
        )
        st.session_state.builder_nutrition = edited

    with tab_req:
        st.caption("Minimum daily nutritional requirements per person.")

        if st.button("Load standard requirements (WHO)"):
            template = pd.DataFrame([
                {"nutrient_name": "Energy(kcal)", "min_per_person_day": 2100},
                {"nutrient_name": "Protein(g)", "min_per_person_day": 52.5},
                {"nutrient_name": "Fat(g)", "min_per_person_day": 49.25},
                {"nutrient_name": "Calcium(mg)", "min_per_person_day": 1100},
                {"nutrient_name": "Iron(mg)", "min_per_person_day": 22},
                {"nutrient_name": "VitaminA(ug)", "min_per_person_day": 500},
                {"nutrient_name": "ThiamineB1(mg)", "min_per_person_day": 0.9},
                {"nutrient_name": "RiboflavinB2(mg)", "min_per_person_day": 1.4},
                {"nutrient_name": "NicacinB3(mg)", "min_per_person_day": 12},
                {"nutrient_name": "Folate(ug)", "min_per_person_day": 160},
                {"nutrient_name": "VitaminC(mg)", "min_per_person_day": 28},
                {"nutrient_name": "Iodine(ug)", "min_per_person_day": 150},
            ])
            st.session_state.builder_requirements = template
            st.rerun()

        edited_req = st.data_editor(
            st.session_state.builder_requirements,
            width="stretch",
            num_rows="dynamic",
        )
        st.session_state.builder_requirements = edited_req


def _render_export():
    st.subheader("Export & Load Scenario")

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Scenario name", st.session_state.builder_meta["name"])
        st.session_state.builder_meta["name"] = name
    with col2:
        desc = st.text_area("Description", st.session_state.builder_meta["description"], height=68)
        st.session_state.builder_meta["description"] = desc

    # Summary
    n_nodes = len(st.session_state.builder_nodes)
    n_edges = len(st.session_state.builder_edges)
    n_comms = len(st.session_state.builder_commodities)
    n_costs = len(st.session_state.builder_costs)
    n_nutr = len(st.session_state.builder_nutrition)

    st.markdown(
        f"**Summary**: {n_nodes} nodes, {n_edges} routes, {n_comms} commodities, "
        f"{n_costs} price entries, {n_nutr} nutrition entries"
    )

    col_load, col_download = st.columns(2)

    with col_load:
        if st.button("📦 Load into Simulator", type="primary", width="stretch"):
            try:
                scenario = _build_scenario_from_state()
                st.session_state["scenario"] = scenario
                st.session_state["scenario_name"] = scenario.name
                st.success(f"Scenario '{scenario.name}' loaded into simulator!")
            except Exception as e:
                st.error(f"Validation error: {e}")

    with col_download:
        if st.button("💾 Download as ZIP", width="stretch"):
            try:
                zip_buffer = _export_zip()
                st.download_button(
                    "Download scenario.zip",
                    data=zip_buffer,
                    file_name=f"{name.replace(' ', '_').lower()}_scenario.zip",
                    mime="application/zip",
                )
            except Exception as e:
                st.error(f"Export error: {e}")


def _build_scenario_from_state() -> Scenario:
    """Build a Scenario from the builder state."""
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write scenario.json
        meta = {
            "name": st.session_state.builder_meta["name"],
            "description": st.session_state.builder_meta["description"],
            "currency": "USD",
            "weight_unit": "metric_ton",
            "time_unit": "day",
            "num_periods": 1,
            "budget": None,
        }
        with open(os.path.join(tmpdir, "scenario.json"), "w") as f:
            json.dump(meta, f)

        # Write CSVs
        st.session_state.builder_nodes.to_csv(os.path.join(tmpdir, "nodes.csv"), index=False)
        st.session_state.builder_edges.to_csv(os.path.join(tmpdir, "edges.csv"), index=False)
        st.session_state.builder_commodities.to_csv(os.path.join(tmpdir, "commodities.csv"), index=False)
        st.session_state.builder_costs.to_csv(os.path.join(tmpdir, "procurement_costs.csv"), index=False)
        st.session_state.builder_nutrition.to_csv(os.path.join(tmpdir, "nutrition.csv"), index=False)
        st.session_state.builder_requirements.to_csv(os.path.join(tmpdir, "nutrition_requirements.csv"), index=False)

        # Diet constraints (empty or default)
        pd.DataFrame({
            "constraint_id": ["carb_protein_ratio", "carb_fat_ratio"],
            "expression": ["carbs >= 4 * Protein(g)", "carbs >= 4 * Fat(g)"],
            "description": [
                "Carb to protein ratio >= 4:1 by mass",
                "Carb to fat ratio >= 4:1 by mass",
            ],
        }).to_csv(os.path.join(tmpdir, "diet_constraints.csv"), index=False)

        return Scenario.load(tmpdir)


def _export_zip() -> bytes:
    """Export builder state as a zip file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        meta = json.dumps({
            "name": st.session_state.builder_meta["name"],
            "description": st.session_state.builder_meta["description"],
            "currency": "USD", "weight_unit": "metric_ton",
            "time_unit": "day", "num_periods": 1, "budget": None,
        }, indent=2)
        zf.writestr("scenario.json", meta)
        zf.writestr("nodes.csv", st.session_state.builder_nodes.to_csv(index=False))
        zf.writestr("edges.csv", st.session_state.builder_edges.to_csv(index=False))
        zf.writestr("commodities.csv", st.session_state.builder_commodities.to_csv(index=False))
        zf.writestr("procurement_costs.csv", st.session_state.builder_costs.to_csv(index=False))
        zf.writestr("nutrition.csv", st.session_state.builder_nutrition.to_csv(index=False))
        zf.writestr("nutrition_requirements.csv", st.session_state.builder_requirements.to_csv(index=False))
    buffer.seek(0)
    return buffer.getvalue()
