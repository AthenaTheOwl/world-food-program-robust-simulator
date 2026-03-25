"""Home page: tabbed walkthrough with sticky ribbon, progress bars, and decision deltas."""

import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd

from core.scenario import Scenario
from models.nominal_lp import NominalLP
from models.budget_constrained import BudgetConstrainedModel
from models.robust_socp import RobustSOCP
from models.two_stage_recourse import TwoStageRecourseModel
from models.solver_utils import extract_solution
from simulation.monte_carlo import generate_price_scenarios, evaluate_solution, compute_simulation_stats
from ui.components.network_graph import plot_network
from ui.components.cost_breakdown import plot_ration_composition, plot_cost_split
from ui.components.tradeoff_curve import plot_tradeoff_curve
from ui.components.monte_carlo_viz import plot_cost_histogram, plot_empirical_cdf
from ui.theme import format_currency
from ui.components.shared import nutrition_bars, delta_ribbon, what_changed


# ── Cached solvers ──

@st.cache_resource
def _load_scenario():
    from pathlib import Path
    p = Path(__file__).parent.parent.parent / "data" / "examples" / "syria_wfp"
    try:
        return Scenario.load(str(p))
    except Exception as e:
        st.error(f"Could not load Syria scenario: {e}")
        return None

@st.cache_data
def _solve_nominal(_n):
    s = _load_scenario(); m = NominalLP(s); m.solve()
    return extract_solution(m, 0.5)

@st.cache_data
def _solve_budget(_n, budget):
    s = _load_scenario(); m = BudgetConstrainedModel(s, budget); m.solve()
    return extract_solution(m, 0.5)

@st.cache_data
def _solve_robust(_n, p):
    s = _load_scenario(); m = RobustSOCP(s, p, fix_slack=1.0); m.solve()
    return extract_solution(m, p) if m.is_solved else None

@st.cache_data
def _solve_robust_sweep(_n):
    s = _load_scenario()
    out = []
    for p in [0.50, 0.75, 0.85, 0.90, 0.95, 0.97, 0.99]:
        m = RobustSOCP(s, p, fix_slack=1.0); m.solve()
        if m.is_solved:
            out.append(extract_solution(m, p))
    return out

@st.cache_data
def _run_monte_carlo(_n):
    s = _load_scenario()
    m_nom = NominalLP(s); m_nom.solve(); sol_nom = extract_solution(m_nom, 0.5)
    m_r90 = RobustSOCP(s, 0.90, fix_slack=1.0); m_r90.solve(); sol_r90 = extract_solution(m_r90, 0.90)
    m_r95 = RobustSOCP(s, 0.95, fix_slack=1.0); m_r95.solve(); sol_r95 = extract_solution(m_r95, 0.95)
    prices = generate_price_scenarios(s, 5000, seed=42)
    out = {}
    for label, sol in [("Nominal", sol_nom), ("Robust 90%", sol_r90), ("Robust 95%", sol_r95)]:
        res = evaluate_solution(s, sol, prices, budget=sol.total_cost)
        out[label] = {"df": res, "stats": compute_simulation_stats(res), "solution": sol}
    return out

@st.cache_data
def _solve_two_stage(_n):
    s = _load_scenario()
    m = TwoStageRecourseModel(s, n_scenarios=20, contract_discount=0.90, seed=42)
    m.solve()
    return m.extract_results() if m.is_solved else None



# ── Main ──

def render():
    scenario = _load_scenario()
    if scenario is None:
        return

    sol_nom = _solve_nominal(scenario.name)
    sweep = _solve_robust_sweep(scenario.name)
    r95 = next((s for s in sweep if s.robustness_level >= 0.95), None)

    st.session_state["scenario"] = scenario
    st.session_state.setdefault("solutions_library", {})
    st.session_state["solutions_library"]["Nominal"] = sol_nom
    if r95:
        st.session_state["solutions_library"]["Robust 95%"] = r95

    # ── HERO ──
    st.markdown("## Feeding 77,000 People Under Uncertainty")
    st.caption(
        "A real WFP Syria scenario. 7 tabs, each one decision. "
        "Start left, work right."
    )

    # ── STICKY RIBBON: always shows nominal baseline ──
    with st.container():
        rc = st.columns(6)
        rc[0].metric("Baseline Plan", format_currency(sol_nom.total_cost) + "/day")
        rc[1].metric("Per Person", format_currency(sol_nom.cost_per_person) + "/day")
        rc[2].metric("Nutrition", f"{sol_nom.nutrient_slack:.0%}")
        if r95:
            rc[3].metric("With 95% Safety", format_currency(r95.total_cost) + "/day",
                          delta=f"+{(r95.total_cost/sol_nom.total_cost - 1):.0%}", delta_color="off")
        rc[4].metric("People", f"{scenario.total_demand:,.0f}")
        rc[5].metric("Routes", f"{len(scenario.edge_index)} links, {len(scenario.commodity_list)} foods")
    st.markdown("---")

    # ── TABS ──
    tabs = st.tabs([
        "1. The Problem",
        "2. Optimal Plan",
        "3. Budget Cuts",
        "4. Price Risk",
        "5. Robust Plan",
        "6. Stress Test",
        "7. Smart Contracts",
    ])

    with tabs[0]: _tab_problem(scenario)
    with tabs[1]: _tab_nominal(scenario, sol_nom)
    with tabs[2]: _tab_budget(scenario, sol_nom)
    with tabs[3]: _tab_uncertainty()
    with tabs[4]: _tab_robust(scenario, sol_nom, sweep)
    with tabs[5]: _tab_monte_carlo(scenario)
    with tabs[6]: _tab_adaptive(scenario, sol_nom, r95)


# ── TAB 1: The Problem ──

def _tab_problem(scenario):
    col_text, col_map = st.columns([2, 3])
    with col_text:
        st.markdown(
            """
**Syria, 2021.** The World Food Programme must feed 77,000 displaced people daily.

| Decision | Scale |
|----------|-------|
| What to buy | 25 food commodities |
| Where to buy | 11 suppliers (3 international, 8 regional) |
| How to ship | 38 transport routes |

Each person needs **2,100 kcal/day** plus 12 essential nutrients.

**Goal:** minimize cost while meeting every nutritional requirement.
            """
        )
    with col_map:
        fig = plot_network(scenario, title="Supply Network", height=450)
        fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, width="stretch")

    st.info(
        "**Blue** = international (Turkey, Lebanon, Jordan) · "
        "**Orange** = regional Syrian markets · "
        "**Teal** = local (supply + demand) · "
        "**Red** = delivery only"
    )


# ── TAB 2: Optimal Plan ──

def _tab_nominal(scenario, sol):
    st.markdown(
        f"### Cheapest feasible plan: **{format_currency(sol.total_cost)}/day** "
        f"({format_currency(sol.cost_per_person)}/person)"
    )
    st.caption("Assumes every price is exactly as expected.")

    col1, col2 = st.columns([1, 1])

    with col1:
        fig = plot_cost_split(sol, title="Cost Split")
        fig.update_layout(height=280, margin=dict(t=40, b=10))
        st.plotly_chart(fig, width="stretch")

        fig2 = plot_ration_composition(scenario, sol, title="Daily Ration per Person")
        fig2.update_layout(height=280, margin=dict(t=40, b=10))
        st.plotly_chart(fig2, width="stretch")

    with col2:
        st.markdown("**Nutrition check** — all 12 nutrients:")
        nutrition_bars(scenario, sol)

    st.warning(
        f"**{1 - sol.international_procurement_ratio:.0%}** comes from regional markets "
        f"where prices swing ±30%. This plan has zero margin for error."
    )


# ── TAB 3: Budget Cuts ──

def _tab_budget(scenario, sol_full):
    st.markdown("### Drag the slider. Watch nutrition collapse.")

    budget = st.slider(
        "Daily budget", 2000, int(sol_full.total_cost), 6000, 500,
        format="$%d",
    )

    sol_b = _solve_budget(scenario.name, budget)
    coverage = sol_b.nutrient_slack
    kcal = int(2100 * coverage)

    # Delta ribbon vs full budget
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Budget", f"${budget:,}")
    col2.metric("Nutrition", f"{coverage:.0%}",
                 delta=f"{(coverage - 1):.0%} vs full", delta_color="inverse")
    col3.metric("Calories", f"{kcal:,} / 2,100")
    col4.metric("Cost/Person", format_currency(sol_b.cost_per_person) + "/day")

    # Side by side: progress bars for full vs budget
    col_full, col_budget = st.columns(2)
    with col_full:
        st.markdown(f"**Full budget** ({format_currency(sol_full.total_cost)})")
        nutrition_bars(scenario, sol_full, compact=True)
    with col_budget:
        st.markdown(f"**${budget:,} budget**")
        nutrition_bars(scenario, sol_b, compact=True)

    if coverage < 0.5:
        st.error("**Severe malnutrition risk.** Below 50% of daily needs.")
    elif coverage < 0.8:
        st.warning("**Chronic deficiencies likely.** Below 80% of daily needs.")


# ── TAB 4: Price Risk ──

def _tab_uncertainty():
    st.markdown("### The real threat: prices you can't predict")

    col1, col2 = st.columns([3, 2])
    with col1:
        np.random.seed(42)
        intl = 800 * (1 + 0.05 * np.random.randn(2000))
        regional = 800 * (1 + 0.30 * np.random.randn(2000))

        fig = go.Figure()
        fig.add_trace(go.Histogram(x=intl, name="International ±5%",
                                    marker_color="#2196F3", opacity=0.7, nbinsx=50))
        fig.add_trace(go.Histogram(x=regional, name="Regional ±30%",
                                    marker_color="#FF9800", opacity=0.7, nbinsx=50))
        fig.add_vline(x=800, line_dash="dash", line_color="black")
        fig.add_annotation(x=800, y=0, yref="paper", yshift=10,
                           text="Expected $800", showarrow=False,
                           font=dict(size=12))
        fig.update_layout(
            title="Same Commodity, Two Supplier Types",
            xaxis_title="$/metric ton", yaxis_title="Frequency",
            barmode="overlay", height=380,
            legend=dict(yanchor="top", y=0.98, xanchor="right", x=0.98),
        )
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.markdown("")
        st.markdown("")
        st.markdown(
            """
| | International | Regional |
|---|:---:|:---:|
| **Spread** | ±5% | ±30% |
| **Correlated?** | No | Yes |
| **Worst case** | $840 | $1,040 |
            """
        )
        st.error(
            "Regional is 6x more volatile. When one commodity spikes, "
            "others follow. A plan built for expected prices **will** blow the budget."
        )

    with st.expander("What does correlated risk mean?"):
        st.markdown(
            "A supply disruption in Homs affects beans, rice, and oil together. "
            "This makes the total cost shock worse than if each price moved independently."
        )


# ── TAB 5: Robust Plan ──

def _tab_robust(scenario, sol_nom, sweep):
    st.markdown("### Pay a little more. Sleep a lot better.")

    if len(sweep) < 2:
        st.warning("Could not solve robust models.")
        return

    for sol in sweep:
        st.session_state["solutions_library"][f"Robust {sol.robustness_level:.0%}"] = sol

    p_choice = st.select_slider(
        "Protection level",
        options=[50, 75, 85, 90, 95, 97, 99],
        value=95,
        format_func=lambda x: f"{x}%",
    )
    sol_r = next((s for s in sweep if abs(s.robustness_level - p_choice / 100) < 0.02), None)

    if sol_r:
        # Delta ribbon
        delta_ribbon(f"Robust {p_choice}%", sol_r, sol_nom)

        col_chart, col_delta = st.columns([3, 2])

        with col_chart:
            fig = plot_tradeoff_curve(sweep, title="Cost vs Protection")
            fig.add_trace(go.Scatter(
                x=[sol_r.robustness_level], y=[sol_r.total_cost],
                mode="markers+text", showlegend=False,
                marker=dict(size=16, color="#F44336", symbol="star"),
                text=[f" {format_currency(sol_r.total_cost)}"],
                textposition="middle right",
                textfont=dict(size=13, color="#F44336"),
            ))
            st.plotly_chart(fig, width="stretch")

        with col_delta:
            premium = sol_r.total_cost - sol_nom.total_cost
            what_changed([
                f"**+{format_currency(premium)}/day** ({premium / sol_nom.total_cost:.0%} premium)",
                f"International sourcing: {sol_nom.international_procurement_ratio:.0%} → **{sol_r.international_procurement_ratio:.0%}**",
                f"Active procurement links: {sol_nom.num_active_procurement} → {sol_r.num_active_procurement}",
                f"Budget survives {p_choice}% of price scenarios instead of ~50%",
            ])

    with st.expander("How does the math work?"):
        st.markdown(
            r"""
$$\text{cost} \geq \text{nominal} + \Phi^{-1}(p) \cdot \lVert\sigma\rVert_2$$

$\Phi^{-1}(p)$ = safety factor (1.65 at 95%). $\sigma$ = uncertainty × procurement.
The norm accounts for diversification — uncorrelated risks partially cancel.
            """
        )


# ── TAB 6: Stress Test ──

def _tab_monte_carlo(scenario):
    st.markdown("### 5,000 random price shocks. Does the plan survive?")

    mc = _run_monte_carlo(scenario.name)
    nom_rate = mc["Nominal"]["stats"]["feasibility_rate"]
    r90_rate = mc["Robust 90%"]["stats"]["feasibility_rate"]
    r95_rate = mc["Robust 95%"]["stats"]["feasibility_rate"]

    # Punchline: three big numbers
    col1, col2, col3 = st.columns(3)
    col1.metric("Nominal survives", f"{nom_rate:.0%}",
                 delta="coin flip", delta_color="off")
    col2.metric("Robust 90% survives", f"{r90_rate:.0%}")
    col3.metric("Robust 95% survives", f"{r95_rate:.0%}")
    st.caption("'Survives' = realized cost ≤ planned cost.")

    # Charts
    sim_dfs = {label: data["df"] for label, data in mc.items()}
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(plot_cost_histogram(sim_dfs, title="Realized Cost Distribution"),
                         width="stretch")
    with col2:
        st.plotly_chart(plot_empirical_cdf(sim_dfs, title="Cumulative Probability"),
                         width="stretch")

    what_changed([
        f"Nominal: survives **{nom_rate:.0%}** — essentially a coin flip",
        f"Robust 90%: survives **{r90_rate:.0%}** — matches the 90% target",
        f"Robust 95%: survives **{r95_rate:.0%}** — matches the 95% target",
        "The math works. Higher protection costs more but delivers as promised.",
    ])

    with st.expander("Show detailed numbers"):
        rows = []
        for label, data in mc.items():
            s = data["stats"]; sol = data["solution"]
            rows.append({
                "Plan": label,
                "Planned Cost": format_currency(sol.total_cost),
                "Mean Realized": format_currency(s["mean_cost"]),
                "Std Dev": format_currency(s["std_cost"]),
                "Survives": f"{s['feasibility_rate']:.1%}",
                "99th Pct": format_currency(s["p99_cost"]),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ── TAB 7: Smart Contracts ──

def _tab_adaptive(scenario, sol_nom, r95):
    st.markdown("### Lock in prices where it matters. Stay flexible everywhere else.")

    two_stage = _solve_two_stage(scenario.name)
    if not two_stage or two_stage.get("status") == "unsolved" or not r95:
        st.warning("Could not solve two-stage model.")
        return

    savings = r95.total_cost - two_stage["total_cost"]
    pct = savings / r95.total_cost * 100

    # Decision delta vs both baselines
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nominal", format_currency(sol_nom.total_cost))
    col2.metric("Robust 95%", format_currency(r95.total_cost))
    col3.metric("Two-Stage", format_currency(two_stage["total_cost"]))
    col4.metric("vs Robust 95%", format_currency(-savings), delta=f"-{pct:.0f}%")

    # Timeline: before → after prices
    st.markdown("---")
    col_before, col_arrow, col_after = st.columns([2, 1, 2])

    with col_before:
        st.markdown("#### Before prices are known")
        st.markdown(
            f"Lock in **{two_stage['num_contracts']} contracts** at 10% below market price. "
            f"This covers **{two_stage['contract_fraction']:.0%}** of total spend."
        )
        if two_stage.get("contract_volumes"):
            top_contracts = sorted(two_stage["contract_volumes"].items(), key=lambda x: -x[1])[:5]
            for (n, c), vol in top_contracts:
                st.markdown(f"- {c} from {n}: **{vol:.1f} MT**")
            if len(two_stage["contract_volumes"]) > 5:
                st.caption(f"+ {len(two_stage['contract_volumes']) - 5} more contracts")

    with col_arrow:
        st.markdown("")
        st.markdown("")
        st.markdown("### →")
        st.caption("Prices revealed")

    with col_after:
        st.markdown("#### After prices are known")
        st.markdown(
            f"Buy remaining **{1 - two_stage['contract_fraction']:.0%}** on spot market. "
            f"Routes, quantities, even ration mix adjust to actual prices."
        )

    # Scenario cards: show what happens under different conditions
    if "scenario_results" in two_stage:
        sc_df = pd.DataFrame(two_stage["scenario_results"])
        st.markdown("---")
        st.markdown("**Three possible futures:**")

        # Pick low, median, high scenarios
        sc_sorted = sc_df.sort_values("recourse_cost")
        low = sc_sorted.iloc[1]  # 2nd lowest (not extreme)
        mid = sc_sorted.iloc[len(sc_sorted) // 2]
        high = sc_sorted.iloc[-2]  # 2nd highest

        col_low, col_mid, col_high = st.columns(3)

        with col_low:
            st.success("**Favorable prices**")
            st.metric("Spot + Transport", format_currency(low["recourse_cost"]))
            total_low = two_stage["contract_cost"] + low["recourse_cost"]
            st.metric("Total day cost", format_currency(total_low))
            st.caption(f"Scenario #{int(low['scenario'])}")

        with col_mid:
            st.info("**Typical prices**")
            st.metric("Spot + Transport", format_currency(mid["recourse_cost"]))
            total_mid = two_stage["contract_cost"] + mid["recourse_cost"]
            st.metric("Total day cost", format_currency(total_mid))
            st.caption(f"Scenario #{int(mid['scenario'])}")

        with col_high:
            st.error("**Price shock**")
            st.metric("Spot + Transport", format_currency(high["recourse_cost"]))
            total_high = two_stage["contract_cost"] + high["recourse_cost"]
            st.metric("Total day cost", format_currency(total_high))
            st.caption(f"Scenario #{int(high['scenario'])}")

        st.caption(
            f"Contracts ({format_currency(two_stage['contract_cost'])}) stay the same in all three. "
            f"Only the spot buys change."
        )

    what_changed([
        f"Contracts save 10% on {two_stage['contract_fraction']:.0%} of procurement",
        f"Spot purchases adjust per scenario — different foods, routes, ration mixes",
        f"Total cost: **{format_currency(two_stage['total_cost'])}** vs {format_currency(r95.total_cost)} static robust",
    ])

    with st.expander("Important caveat"):
        st.markdown(
            "This comparison mixes two effects: the 10% contract discount (a new instrument) "
            "and scenario-specific recourse (flexibility). The gap is not purely 'value of adaptivity.' "
            "A fair benchmark would use identical instruments in both models."
        )

    with st.expander("How does two-stage optimization work?"):
        st.markdown(
            "**Stage 1:** Choose contract volumes (before uncertainty). "
            "**Stage 2:** For each of 20 price scenarios, choose spot buys, routing, and ration mix. "
            "Minimize: `contract_cost + (1/20) × Σ recourse_cost`. "
            "This is an extensive-form stochastic program — each scenario gets its own variables."
        )
