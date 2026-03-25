"""Page 3: Optimization — select model, configure parameters, solve."""

import streamlit as st

from core.scenario import Scenario
from models.nominal_lp import NominalLP
from models.budget_constrained import BudgetConstrainedModel
from models.robust_socp import RobustSOCP
from models.solver_utils import extract_solution, solution_to_metrics_dict, SolutionResult
from ui.tooltips import get_tooltip, get_tooltip_body
from config import DEFAULT_BUDGET, DEFAULT_ROBUSTNESS


def render():
    st.header("Optimization")

    if "scenario" not in st.session_state:
        st.warning("Please load a scenario first from the **Scenario Manager** page.")
        return

    scenario: Scenario = st.session_state["scenario"]
    st.markdown(f"**Scenario:** {scenario.name} — {scenario.total_demand:,.0f} people")

    # Model selection
    col_model, col_info = st.columns([2, 3])

    with col_model:
        model_type = st.selectbox(
            "Optimization Model",
            options=["Nominal (Min Cost)", "Budget-Constrained", "Robust (SOCP)", "Robustness Sweep"],
            help=get_tooltip_body("nominal_lp"),
        )

    with col_info:
        if model_type == "Nominal (Min Cost)":
            st.info(get_tooltip_body("nominal_lp"))
        elif model_type == "Budget-Constrained":
            st.info(get_tooltip_body("budget_constrained"))
        elif model_type == "Robust (SOCP)":
            st.info(get_tooltip_body("robust_socp"))
        else:
            st.info("Solve across a range of robustness levels to see the cost-protection tradeoff.")

    # Parameters
    st.subheader("Parameters")

    budget = None
    robustness = 0.5
    fix_slack = 1.0

    if model_type == "Budget-Constrained":
        budget = st.slider(
            "Daily Budget ($)",
            min_value=1000.0,
            max_value=20000.0,
            value=DEFAULT_BUDGET,
            step=100.0,
            help=get_tooltip_body("budget"),
        )
        fix_slack = None  # slack is free to be maximized

    elif model_type == "Robust (SOCP)":
        robustness = st.slider(
            "Robustness Level (p)",
            min_value=0.50,
            max_value=0.995,
            value=DEFAULT_ROBUSTNESS,
            step=0.01,
            format="%.2f",
            help=get_tooltip_body("robustness_level"),
        )

        mode = st.radio(
            "Budget Mode",
            ["Unlimited Budget (minimize cost)", "Fixed Budget (maximize nutrition)"],
            horizontal=True,
        )
        if "Fixed" in mode:
            budget = st.slider(
                "Daily Budget ($)", 1000.0, 20000.0, DEFAULT_BUDGET, 100.0,
                help=get_tooltip_body("budget"),
            )
            fix_slack = None
        else:
            fix_slack = 1.0

    elif model_type == "Robustness Sweep":
        mode = st.radio(
            "Budget Mode",
            ["Unlimited Budget (minimize cost)", "Fixed Budget (maximize nutrition)"],
            horizontal=True,
        )
        if "Fixed" in mode:
            budget = st.slider(
                "Daily Budget ($)", 1000.0, 20000.0, DEFAULT_BUDGET, 100.0,
                help=get_tooltip_body("budget"),
            )

    # Solve button
    if st.button("🔧 Solve", type="primary", width="stretch"):
        if model_type == "Robustness Sweep":
            _solve_sweep(scenario, budget)
        else:
            _solve_single(scenario, model_type, budget, robustness, fix_slack)

    # Show cached results
    if "current_solution" in st.session_state:
        sol = st.session_state["current_solution"]
        _display_solution_summary(sol)

    if "sweep_solutions" in st.session_state:
        _display_sweep_summary(st.session_state["sweep_solutions"])


def _solve_single(scenario, model_type, budget, robustness, fix_slack):
    """Solve a single optimization model."""
    with st.spinner("Solving..."):
        try:
            if model_type == "Nominal (Min Cost)":
                model = NominalLP(scenario)
                robustness = 0.5
            elif model_type == "Budget-Constrained":
                model = BudgetConstrainedModel(scenario, budget)
                robustness = 0.5
            else:  # Robust SOCP
                model = RobustSOCP(
                    scenario,
                    robustness_level=robustness,
                    budget=budget,
                    fix_slack=fix_slack,
                )

            status = model.solve()

            if status in ("optimal", "optimal_inaccurate"):
                solution = extract_solution(model, robustness_level=robustness)
                st.session_state["current_solution"] = solution
                st.session_state["current_model_type"] = model_type

                # Store in solutions library for comparison
                if "solutions_library" not in st.session_state:
                    st.session_state["solutions_library"] = {}
                label = f"{model_type} (p={robustness:.0%})"
                if budget:
                    label += f" B=${budget:,.0f}"
                st.session_state["solutions_library"][label] = solution

                st.success(f"Solved! Status: {status}")
            else:
                st.error(f"Solver returned: {status}")
        except Exception as e:
            st.error(f"Optimization failed: {e}")


def _solve_sweep(scenario, budget):
    """Solve across a range of robustness levels."""
    pofs = [0.50, 0.75, 0.85, 0.90, 0.92, 0.95, 0.96, 0.97, 0.98, 0.99, 0.995]

    progress = st.progress(0, text="Solving robustness sweep...")
    solutions = []

    for i, pof in enumerate(pofs):
        progress.progress((i + 1) / len(pofs), text=f"Solving p={pof:.1%}...")
        try:
            if budget is not None:
                model = RobustSOCP(scenario, robustness_level=pof, budget=budget, fix_slack=None)
            else:
                model = RobustSOCP(scenario, robustness_level=pof, fix_slack=1.0)

            status = model.solve()
            if status in ("optimal", "optimal_inaccurate"):
                sol = extract_solution(model, robustness_level=pof)
                solutions.append(sol)
        except Exception as e:
            st.warning(f"Failed at p={pof:.1%}: {e}")

    progress.empty()

    if solutions:
        st.session_state["sweep_solutions"] = solutions
        # Store all in library
        if "solutions_library" not in st.session_state:
            st.session_state["solutions_library"] = {}
        for sol in solutions:
            label = f"Robust p={sol.robustness_level:.0%}"
            st.session_state["solutions_library"][label] = sol
        st.success(f"Completed! {len(solutions)}/{len(pofs)} solved successfully.")
    else:
        st.error("No solutions found.")


def _display_solution_summary(sol: SolutionResult):
    """Display summary metrics for a single solution."""
    st.subheader("Solution Summary")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Cost", f"${sol.total_cost:,.0f}")
    with col2:
        st.metric("Nutrient Slack", f"{sol.nutrient_slack:.3f}")
    with col3:
        st.metric("Cost/Person", f"${sol.cost_per_person:,.2f}")
    with col4:
        st.metric("Robustness", f"{sol.robustness_level:.0%}")

    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric("Procurement %", f"{sol.procurement_ratio:.1%}",
                   help=get_tooltip_body("procurement_ratio"))
    with col6:
        st.metric("Transport %", f"{sol.transportation_ratio:.1%}")
    with col7:
        st.metric("Intl Procurement %", f"{sol.international_procurement_ratio:.1%}",
                   help=get_tooltip_body("international_ratio"))
    with col8:
        st.metric("Active Routes", sol.num_active_transport)

    st.caption("Go to **Results** page for detailed visualizations.")


def _display_sweep_summary(solutions: list[SolutionResult]):
    """Display summary table for robustness sweep."""
    import pandas as pd
    from ui.components.tradeoff_curve import plot_tradeoff_curve

    st.subheader("Robustness Sweep Results")

    # Tradeoff curve
    fig = plot_tradeoff_curve(solutions, title="Cost vs. Robustness Level")
    st.plotly_chart(fig, width="stretch")

    # Summary table
    rows = [solution_to_metrics_dict(s) for s in solutions]
    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch")

    st.caption("Go to **Results** page for detailed visualizations of any specific solution.")
