# Food Relief Optimizer

An interactive simulator for humanitarian food relief planning under uncertainty, built on a real World Food Programme scenario in Syria.

**[Live demo →](http://localhost:8501)** (run locally with `streamlit run app.py`)

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Streamlit](https://img.shields.io/badge/streamlit-1.40+-red)
![License](https://img.shields.io/badge/license-MIT-green)

## What This Does

77,000 displaced people in Syria need food daily. This app shows how different optimization approaches handle the real planning decisions: what to buy, where to source it, how to ship it — and what happens when prices spike, routes close, or budgets get cut.

**The guided overview walks through 7 steps:**

| Step | Question | Method |
|------|----------|--------|
| 1. The Problem | What does the supply network look like? | Data visualization |
| 2. Optimal Plan | What's the cheapest way to feed everyone? | Linear programming |
| 3. Budget Cuts | What happens when money runs out? | Budget-constrained LP |
| 4. Price Risk | How volatile are regional vs international prices? | Uncertainty modeling |
| 5. Robust Plan | How much extra to spend for 95% safety? | Second-order cone program |
| 6. Stress Test | Does the theory hold under 5,000 random shocks? | Monte Carlo simulation |
| 7. Smart Contracts | Can contracts + flexibility beat static robustness? | Two-stage stochastic program |

## Key Results (Syria WFP Scenario)

| Metric | Value |
|--------|-------|
| Nominal cost | $31,046/day |
| Robust 95% cost | $35,565/day (+15%) |
| Two-stage adaptive | $28,201/day |
| Budget $6k → nutrition | 19.3% coverage |
| Monte Carlo calibration | 50.8% / 90.1% / 95.1% |

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/food-relief-optimizer.git
cd food-relief-optimizer
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. The Syria WFP scenario loads automatically.

## Project Structure

```
food-relief-simulator/
├── app.py                     # Streamlit entry point
├── config.py                  # App-wide constants
├── requirements.txt
│
├── core/
│   ├── scenario.py            # Scenario dataclass + loader
│   └── validators.py          # Data validation
│
├── models/
│   ├── base_model.py          # Shared multi-commodity flow constraints
│   ├── nominal_lp.py          # Deterministic cost minimization
│   ├── budget_constrained.py  # Maximize nutrition under budget
│   ├── robust_socp.py         # Ellipsoidal robust optimization
│   ├── adaptive_robust.py     # Affine decision rules (SOCP approx)
│   ├── two_stage_recourse.py  # Finite-scenario two-stage (vectorized)
│   ├── multi_period.py        # Multi-day planning with inventory
│   └── solver_utils.py        # Solution extraction + metrics
│
├── simulation/
│   └── monte_carlo.py         # Price scenario generation + evaluation
│
├── ui/
│   ├── pages/
│   │   ├── 00_home.py         # Guided overview (Story Mode)
│   │   ├── 01_scenario_manager.py
│   │   ├── 02_scenario_builder.py
│   │   ├── 03_optimization.py
│   │   ├── 04_results.py      # Results dashboard
│   │   ├── 05_disruption_lab.py
│   │   ├── 06_multi_period.py
│   │   ├── 07_monte_carlo.py  # Monte Carlo stress test
│   │   ├── 08_comparison.py
│   │   └── 09_adaptive.py     # Adaptive contracts
│   ├── components/
│   │   ├── shared.py          # Reusable: ribbons, progress bars, deltas
│   │   ├── network_graph.py
│   │   ├── sankey.py
│   │   ├── nutrition_radar.py
│   │   ├── cost_breakdown.py
│   │   ├── tradeoff_curve.py
│   │   └── monte_carlo_viz.py
│   ├── theme.py
│   └── tooltips.py
│
├── data/examples/syria_wfp/   # Pre-loaded scenario
│   ├── scenario.json
│   ├── nodes.csv
│   ├── edges.csv
│   ├── commodities.csv
│   ├── nutrition.csv
│   ├── procurement_costs.csv
│   ├── nutrition_requirements.csv
│   └── diet_constraints.csv
│
└── tests/
    └── test_hybrid_nodes.py
```

## Modeling Notes

**Hybrid nodes:** Local markets (Hassakeh, Dara, etc.) both procure food and serve local demand. The model enforces `procurement + inflow = outflow + local_delivery` at every node — this matters because without it, demand nodes appear served without corresponding flow.

**Uncertainty model:** International suppliers have ±5% price volatility (independent). Regional suppliers have ±30% volatility with cross-commodity correlation within each market.

**Two-stage caveat:** The adaptive model comparison is not pure "value of adaptivity" — it combines discounted contracts (a new instrument) with scenario-specific recourse (flexibility). See the in-app caveats for details.

## Based On

- MIT 15.094 Homework 3 (2021): Syria WFP food assistance case
- Bertsimas & Tsitsiklis, *Introduction to Linear Optimization*
- Boyd & Vandenberghe, *Convex Optimization*
- Bertsimas, Sim, & Zhang, *Robust Optimization*

## License

MIT
