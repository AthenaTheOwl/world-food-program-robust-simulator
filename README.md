<!-- ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ -->

# N° 04 · food relief optimizer

> *humanitarian logistics, under uncertainty.*

77,000 displaced people in syria. an interactive simulator that walks through what happens when you actually have to plan it: what to buy, where to source it, how to ship it — and what to do when prices spike, routes close, or the budget gets cut.

`python` · `streamlit` · `cvxpy` · `MIT` · 2024 · **status: solved**

[**open the demo →**](http://localhost:8501) (run locally with `streamlit run app.py`)

<!-- ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ -->

## the seven rooms

a guided tour. each room is a different question and a different method.

| Room | Question | Method |
|------|----------|--------|
| 1 · the problem        | what does the supply network look like?         | data viz |
| 2 · the optimal plan   | cheapest way to feed everyone?                  | linear program |
| 3 · the budget cuts    | what happens when the money runs out?           | budget-constrained LP |
| 4 · the price risk     | how volatile are regional vs international prices? | uncertainty modeling |
| 5 · the robust plan    | how much extra to spend for 95% safety?         | second-order cone program |
| 6 · the stress test    | does the theory hold under 5,000 random shocks? | monte carlo |
| 7 · the smart contracts| can contracts + flexibility beat static robustness? | two-stage stochastic program |

## what came back

the syria WFP scenario, with the dial turned in different directions.

| metric                   | value             |
|--------------------------|-------------------|
| nominal cost             | $31,046 / day     |
| robust 95% cost          | $35,565 / day · *+15%* |
| two-stage adaptive       | $28,201 / day     |
| budget $6k → nutrition   | 19.3% coverage    |
| monte carlo calibration  | 50.8% / 90.1% / 95.1% |

## quick start

```bash
git clone https://github.com/AthenaTheOwl/world-food-program-robust-simulator.git
cd world-food-program-robust-simulator
pip install -r requirements.txt
streamlit run app.py
```

open `http://localhost:8501`. the syria scenario loads itself.

<!-- ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ -->

## the floorplan

```
food-relief-simulator/
├── app.py                     # streamlit entry
├── config.py                  # constants
├── requirements.txt
│
├── core/
│   ├── scenario.py            # scenario dataclass + loader
│   └── validators.py
│
├── models/
│   ├── base_model.py          # shared multi-commodity flow constraints
│   ├── nominal_lp.py          # deterministic cost minimization
│   ├── budget_constrained.py  # maximize nutrition under budget
│   ├── robust_socp.py         # ellipsoidal robust optimization
│   ├── adaptive_robust.py     # affine decision rules (SOCP approx)
│   ├── two_stage_recourse.py  # finite-scenario two-stage
│   ├── multi_period.py        # multi-day with inventory
│   └── solver_utils.py
│
├── simulation/
│   └── monte_carlo.py         # price scenarios + evaluation
│
├── ui/
│   ├── pages/                 # one page per room
│   ├── components/            # network graphs, sankeys, radar charts
│   └── theme.py
│
├── data/examples/syria_wfp/   # the pre-loaded scenario
└── tests/
```

## modeling notes

**hybrid nodes.** local markets — hassakeh, dara, others — both procure food and serve local demand. the model enforces `procurement + inflow = outflow + local_delivery` at every node. without it, demand nodes look served without any flow reaching them. they aren't.

**uncertainty.** international suppliers carry ±5% price volatility, independent. regional suppliers carry ±30%, with cross-commodity correlation inside each market.

**a caveat.** the adaptive comparison is not a pure measure of "value of adaptivity." it combines discounted contracts (a new instrument) with scenario-specific recourse (flexibility). the in-app notes go deeper.

<!-- ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ -->

## colophon

based on:
- MIT 15.094 homework 3 (2021), syria WFP food assistance
- bertsimas & tsitsiklis, *introduction to linear optimization*
- boyd & vandenberghe, *convex optimization*
- bertsimas, sim, & zhang, *robust optimization*

`MIT` license. *built downstairs.* — [the basement, room 7](https://github.com/AthenaTheOwl)
