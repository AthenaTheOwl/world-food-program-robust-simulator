"""Shared UI components used across Story Mode and Analyst pages.

These patterns originated in 00_home.py and are extracted here so every page
can present information consistently: punchline first, progress bars over radar,
decision deltas over raw tables.
"""

import streamlit as st

from core.scenario import Scenario
from models.solver_utils import SolutionResult
from ui.theme import format_currency


def nutrition_bars(scenario: Scenario, sol: SolutionResult, compact: bool = False):
    """Render nutrition as horizontal progress bars.

    Much easier to scan than a radar chart. Each nutrient shows as a labeled
    progress bar with the fulfillment percentage.

    Args:
        scenario: Scenario with nutrient requirements.
        sol: Solved solution with nutrients_pp values.
        compact: If True, use a two-column layout (label | bar).
    """
    for nutrient in scenario.nutrient_list:
        req = scenario.get_requirement(nutrient)
        actual = sol.nutrients_pp.get(nutrient, 0)
        pct = actual / req if req > 0 else 0
        short = nutrient.split("(")[0].strip()
        clamped = min(pct, 1.0)

        if compact:
            c1, c2 = st.columns([1, 3])
            with c1:
                st.caption(short)
            with c2:
                st.progress(clamped, text=f"{pct:.0%}")
        else:
            st.progress(clamped, text=f"{short}: **{pct:.0%}**")


def delta_ribbon(label: str, sol: SolutionResult, sol_baseline: SolutionResult):
    """Show a compact comparison ribbon: this plan vs a baseline.

    Displays five metrics in a row: plan name, cost delta, coverage,
    sourcing shift, and cost per person.
    """
    cost_delta = sol.total_cost - sol_baseline.total_cost
    cost_pct = cost_delta / sol_baseline.total_cost * 100 if sol_baseline.total_cost else 0
    intl_delta = sol.international_procurement_ratio - sol_baseline.international_procurement_ratio

    cols = st.columns(5)
    cols[0].metric("Plan", label)
    cols[1].metric("Cost", format_currency(sol.total_cost),
                    delta=f"{cost_pct:+.1f}% vs baseline", delta_color="off")
    cols[2].metric("Coverage", f"{sol.nutrient_slack:.0%}")
    cols[3].metric("Int'l Sourcing", f"{sol.international_procurement_ratio:.0%}",
                    delta=f"{intl_delta:+.0%} vs baseline", delta_color="off")
    cols[4].metric("Cost/Person", format_currency(sol.cost_per_person) + "/day")


def what_changed(lines: list[str]):
    """Render a 'What changed?' summary block.

    Each line is a bullet point explaining one concrete consequence of the
    decision being shown on this page/tab.
    """
    st.markdown("**What changed?**")
    for line in lines:
        st.markdown(f"- {line}")


def solution_summary_ribbon(scenario: Scenario, sol: SolutionResult, label: str = "Current Plan"):
    """Compact plan summary — used as a persistent header on analyst pages."""
    cols = st.columns(6)
    cols[0].metric(label, format_currency(sol.total_cost) + "/day")
    cols[1].metric("Per Person", format_currency(sol.cost_per_person))
    cols[2].metric("Nutrition", f"{sol.nutrient_slack:.0%}")
    cols[3].metric("Int'l Share", f"{sol.international_procurement_ratio:.0%}")
    cols[4].metric("Procurement", f"{sol.num_active_procurement} active")
    cols[5].metric("Routes", f"{sol.num_active_transport} active")
    st.markdown("---")


def scenario_card(title: str, style: str, cost: float, detail: str = "", caption: str = ""):
    """Render a scenario outcome card (favorable / typical / shock).

    Args:
        title: Card heading (e.g., "Favorable Prices").
        style: One of "success", "info", "error" for color.
        cost: The cost value to display.
        detail: Optional extra metric or text.
        caption: Optional small text below.
    """
    box = {"success": st.success, "info": st.info, "error": st.error}.get(style, st.info)
    box(f"**{title}**")
    st.metric("Cost", format_currency(cost))
    if detail:
        st.caption(detail)
    if caption:
        st.caption(caption)
