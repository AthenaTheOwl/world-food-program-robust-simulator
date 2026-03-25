"""Food Relief Optimization Simulator — Streamlit entry point."""

import sys
import importlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from config import APP_TITLE, APP_ICON

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ──
st.sidebar.title(f"{APP_ICON} Food Relief Optimizer")

# Story Mode — the guided narrative
st.sidebar.markdown("**Story Mode**")
STORY_PAGES = {
    "Guided Overview": "ui.pages.00_home",
}

# Analyst Tools — deeper inspection
st.sidebar.markdown("**Analyst Tools**")
ANALYST_PAGES = {
    "Optimize": "ui.pages.03_optimization",
    "Results Dashboard": "ui.pages.04_results",
    "Disruption Lab": "ui.pages.05_disruption_lab",
    "Monte Carlo": "ui.pages.07_monte_carlo",
    "Adaptive Contracts": "ui.pages.09_adaptive",
}

# Data / Advanced
st.sidebar.markdown("**Data & Setup**")
DATA_PAGES = {
    "Scenario Manager": "ui.pages.01_scenario_manager",
}
ADVANCED_PAGES = {
    "Scenario Builder": "ui.pages.02_scenario_builder",
    "Multi-Period Planner": "ui.pages.06_multi_period",
    "Comparison": "ui.pages.08_comparison",
}

ALL_PAGES = {**STORY_PAGES, **ANALYST_PAGES, **DATA_PAGES}

page = st.sidebar.radio(
    "Navigate",
    list(ALL_PAGES.keys()),
    label_visibility="collapsed",
)

with st.sidebar.expander("Advanced"):
    adv = st.radio(
        "Pick", [None] + list(ADVANCED_PAGES.keys()),
        format_func=lambda x: "← Back" if x is None else x,
        label_visibility="collapsed",
    )
    if adv:
        page = adv

# ── Status ──
st.sidebar.markdown("---")
if "scenario" in st.session_state:
    sc = st.session_state["scenario"]
    st.sidebar.success(sc.name)
    st.sidebar.caption(
        f"{sc.total_demand:,.0f} people · "
        f"{len(sc.commodity_list)} foods · "
        f"{len(sc.edge_index)} routes"
    )
else:
    st.sidebar.info("No scenario loaded")

n_sols = len(st.session_state.get("solutions_library", {}))
if n_sols:
    st.sidebar.caption(f"{n_sols} plan(s) saved")

st.sidebar.markdown("---")
st.sidebar.caption(
    "Based on MIT 15.094 WFP Syria case study. "
    "Demonstrates optimization under uncertainty for humanitarian logistics."
)

# ── Route ──
all_pages = {**ALL_PAGES, **ADVANCED_PAGES}
mod = importlib.import_module(all_pages[page])
mod.render()
