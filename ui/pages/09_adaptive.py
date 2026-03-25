"""Page 9: Adaptive Contracts — two-stage recourse with timeline and scenario cards."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.scenario import Scenario
from models.adaptive_robust import AdaptiveRobustModel
from models.two_stage_recourse import TwoStageRecourseModel
from models.robust_socp import RobustSOCP
from models.solver_utils import extract_solution
from ui.components.shared import what_changed, solution_summary_ribbon
from ui.tooltips import get_tooltip_body
from ui.theme import format_currency


def render():
    st.header("Adaptive Contracts")
    st.caption(
        "Lock in prices where it matters. Stay flexible everywhere else. "
        "The two-stage model uses discounted contracts + scenario-specific recourse."
    )

    if "scenario" not in st.session_state:
        st.warning("Load a scenario first.")
        return

    scenario: Scenario = st.session_state["scenario"]

    # ── Parameters ──
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        discount = st.slider("Contract Discount (%)", 1, 30, 10, 1)
    with col2:
        n_scenarios = st.slider("Price Scenarios", 5, 50, 20, 5)
    with col3:
        max_contract = st.slider("Max Contract Fraction", 0.1, 1.0, 0.8, 0.1)
    with col4:
        robustness = st.slider("Static Robust p (for comparison)", 0.50, 0.99, 0.95, 0.01)

    if st.button("Solve", type="primary", use_container_width=True):
        with st.spinner("Solving two-stage model..."):
            try:
                model = TwoStageRecourseModel(
                    scenario,
                    n_scenarios=n_scenarios,
                    contract_discount=1 - discount / 100,
                    max_contract_fraction=max_contract,
                )
                status = model.solve()
                if model.is_solved:
                    st.session_state["adp_results"] = model.extract_results()

                    static = RobustSOCP(scenario, robustness, fix_slack=1.0)
                    static.solve()
                    st.session_state["adp_static"] = extract_solution(static, robustness)
                    st.success(f"Solved: {status}")
                else:
                    st.error(f"Solver: {status}")
            except Exception as e:
                st.error(f"Error: {e}")

    if "adp_results" not in st.session_state:
        return

    r = st.session_state["adp_results"]
    static = st.session_state.get("adp_static")

    # ── Punchline metrics ──
    savings = (static.total_cost - r["total_cost"]) if static else 0
    pct = (savings / static.total_cost * 100) if static and static.total_cost else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Two-Stage Cost", format_currency(r["total_cost"]))
    if static:
        col2.metric("Static Robust", format_currency(static.total_cost))
        col3.metric("Difference", format_currency(-savings), delta=f"-{pct:.0f}%")
    col4.metric("Contract Share", f"{r['contract_fraction']:.0%}")

    st.markdown("---")

    # ── Timeline: Before → After ──
    col_before, col_arrow, col_after = st.columns([2, 1, 2])

    with col_before:
        st.markdown("#### Stage 1: Before prices known")
        st.markdown(
            f"Lock in **{r['num_contracts']} contracts** at {discount}% below market."
        )
        if r.get("contract_volumes"):
            top = sorted(r["contract_volumes"].items(), key=lambda x: -x[1])[:5]
            for (n, c), vol in top:
                price = scenario.price_lookup.get((n, c), 0) * (1 - discount / 100)
                st.markdown(f"- {c} from {n}: **{vol:.1f} MT** @ {format_currency(price)}/MT")
            if len(r["contract_volumes"]) > 5:
                st.caption(f"+ {len(r['contract_volumes']) - 5} more")

    with col_arrow:
        st.markdown(""); st.markdown("")
        st.markdown("### →")
        st.caption("Prices revealed")

    with col_after:
        st.markdown("#### Stage 2: After prices known")
        st.markdown(
            f"Buy remaining **{1 - r['contract_fraction']:.0%}** on spot. "
            f"Routes, quantities, and ration mix adjust per scenario."
        )

    # ── Scenario cards: low / typical / shock ──
    if "scenario_results" in r:
        sc_df = pd.DataFrame(r["scenario_results"])
        st.markdown("---")
        st.markdown("**What happens under different price conditions?**")

        sc_sorted = sc_df.sort_values("recourse_cost")
        n = len(sc_sorted)
        low = sc_sorted.iloc[max(1, n // 10)]
        mid = sc_sorted.iloc[n // 2]
        high = sc_sorted.iloc[min(n - 2, n - n // 10)]

        col_l, col_m, col_h = st.columns(3)

        with col_l:
            st.success("**Favorable prices**")
            total_l = r["contract_cost"] + low["recourse_cost"]
            st.metric("Spot + Transport", format_currency(low["recourse_cost"]))
            st.metric("Total", format_currency(total_l))

        with col_m:
            st.info("**Typical prices**")
            total_m = r["contract_cost"] + mid["recourse_cost"]
            st.metric("Spot + Transport", format_currency(mid["recourse_cost"]))
            st.metric("Total", format_currency(total_m))

        with col_h:
            st.error("**Price shock**")
            total_h = r["contract_cost"] + high["recourse_cost"]
            st.metric("Spot + Transport", format_currency(high["recourse_cost"]))
            st.metric("Total", format_currency(total_h))

        st.caption(
            f"Contracts ({format_currency(r['contract_cost'])}) are the same in all three. "
            f"Only spot buys change."
        )

    # ── What changed ──
    what_changed([
        f"Contracts lock in {discount}% savings on {r['contract_fraction']:.0%} of spend",
        f"Spot purchases adjust per scenario — different foods, routes, ration mixes",
        f"Total: **{format_currency(r['total_cost'])}**"
        + (f" vs {format_currency(static.total_cost)} static robust" if static else ""),
    ])

    # ── Detail tables in expanders ──
    with st.expander("Show all contract details"):
        if r.get("contract_volumes"):
            rows = [
                {
                    "Node": n, "Commodity": c,
                    "Volume (MT)": round(v, 3),
                    "Price": format_currency(scenario.price_lookup[(n, c)] * (1 - discount / 100)),
                    "Cost": format_currency(v * scenario.price_lookup[(n, c)] * (1 - discount / 100)),
                }
                for (n, c), v in sorted(r["contract_volumes"].items(), key=lambda x: -x[1])
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.expander("Show all scenario recourse costs"):
        if "scenario_results" in r:
            st.dataframe(pd.DataFrame(r["scenario_results"]), width="stretch", hide_index=True)

    with st.expander("Show average ration"):
        if r.get("ration_pp"):
            items = sorted(r["ration_pp"].items(), key=lambda x: -x[1])
            rows = [{"Commodity": c, "kg/person/day": round(v, 4)} for c, v in items]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    with st.expander("Important caveat"):
        st.markdown(
            "This comparison mixes two effects: the contract discount (a new instrument) "
            "and scenario-specific recourse (flexibility). The gap is not purely 'value of adaptivity.' "
            "A fair benchmark would use identical instruments in both models."
        )
