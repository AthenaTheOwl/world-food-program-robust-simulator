# World Food Program robust simulator

77,000 people need food. The nominal plan costs $31,046 a day. The 95% protected plan costs $35,565. The adaptive contract comes in at $28,201. That is the argument in three invoices.

## What it does

This Streamlit app walks through a food-relief planning problem under uncertainty: what to buy, where to source it, how to ship it, and what breaks when prices spike, routes close, or the budget gets cut.

The pre-loaded scenario is based on a Syria food-assistance exercise.

## Seven rooms

| Room | Question | Method |
|---|---|---|
| 1. The problem | What does the supply network look like? | Data visualization |
| 2. The optimal plan | Cheapest way to feed everyone? | Linear program |
| 3. The budget cut | What happens when money runs out? | Budget-constrained LP |
| 4. The price risk | How volatile are regional and international prices? | Uncertainty modeling |
| 5. The protected plan | How much extra to spend for 95% safety? | Second-order cone program |
| 6. The stress test | Does the theory hold under 5,000 shocks? | Monte Carlo |
| 7. The contracts | Can contracts plus flexibility beat a static plan? | Two-stage stochastic program |

## What came back

| Metric | Value |
|---|---|
| Nominal cost | `$31,046 / day` |
| 95% protected cost | `$35,565 / day`, `+15%` |
| Two-stage adaptive | `$28,201 / day` |
| Budget `$6k` to nutrition | `19.3%` coverage |
| Monte Carlo calibration | `50.8% / 90.1% / 95.1%` |

## Quick start

```bash
git clone https://github.com/AthenaTheOwl/world-food-program-robust-simulator.git
cd world-food-program-robust-simulator
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501`. The Syria scenario loads itself.

## Modeling notes

Hybrid nodes, such as local markets, can both procure food and serve local demand. The model enforces:

```text
procurement + inflow = outflow + local_delivery
```

Without that balance, a demand node can look served while no food reaches it.

International suppliers carry +/-5% price volatility. Regional suppliers carry +/-30%, with cross-commodity correlation inside each market.

The adaptive comparison combines discounted contracts with scenario-specific recourse. It is useful, with the contract discount and the recourse value intertwined.

## Live demo

Deploy with Streamlit Cloud using:

```text
streamlit_app.py
```

Local run:

```bash
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Floorplan

```text
app.py
config.py
requirements.txt
core/
  scenario.py
  validators.py
models/
  base_model.py
  nominal_lp.py
  budget_constrained.py
  robust_socp.py
  adaptive_robust.py
  two_stage_recourse.py
  multi_period.py
  solver_utils.py
simulation/
  monte_carlo.py
ui/
  pages/
  components/
  theme.py
data/examples/syria_wfp/
tests/
```

## Connects to

- `dispatch-optimizer` for the operational dispatch layer after allocation decisions.
- `Robust-Facility-Location` for facility and network placement under uncertain demand.
- `proof-gate-runner` for turning model sanity checks into reusable CI gates.

## References

- MIT 15.094 homework 3 (2021), Syria WFP food assistance.
- Bertsimas and Tsitsiklis, *Introduction to Linear Optimization*.
- Boyd and Vandenberghe, *Convex Optimization*.
- Bertsimas, Sim, and Zhang, *Robust Optimization*.

## License

MIT.
