import json
from pathlib import Path

import numpy as np
import pytest

from core.scenario import Scenario
from models.budget_constrained import BudgetConstrainedModel
from models.solver_utils import extract_solution, unserved_people
from models.two_stage_recourse import TwoStageRecourseModel
from reports.scorecard import (
    MAX_CONTRACT_FRACTION,
    NO_DISCOUNT,
    TWO_STAGE_SCENARIOS,
    TWO_STAGE_SEED,
    decompose,
)

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "data" / "examples" / "syria_wfp"


@pytest.fixture(scope="module")
def scenario():
    return Scenario.load(SCENARIO_DIR)


@pytest.fixture(scope="module")
def rows(scorecard_path):
    lines = scorecard_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _per_scenario_costs(model):
    """Evaluate each price draw directly from the solved decision variables."""
    s = model.scenario
    contract_prices = np.array(
        [model.contract_discount * s.price_lookup[key] for key in s.procurement_index]
    )
    transport_costs = np.array([s.get_transport_cost(a, b) for (a, b) in s.edge_index])
    contract_cost = contract_prices @ model._contract.value
    return np.array(
        [
            contract_cost
            + model.price_scenarios[si] @ sv["spot"].value
            + transport_costs @ sv["transport"].value
            for si, sv in enumerate(model._scenario_vars)
        ]
    )


def _solve(scenario, recourse):
    model = TwoStageRecourseModel(
        scenario,
        n_scenarios=TWO_STAGE_SCENARIOS,
        contract_discount=NO_DISCOUNT,
        max_contract_fraction=MAX_CONTRACT_FRACTION,
        seed=TWO_STAGE_SEED,
        recourse=recourse,
    )
    assert model.solve() == "optimal"
    return model


def test_fixed_plan_uses_one_decision_for_every_price_draw(scenario):
    fixed = _solve(scenario, recourse=False)
    first_spot = fixed._scenario_vars[0]["spot"].value
    for sv in fixed._scenario_vars[1:]:
        np.testing.assert_allclose(sv["spot"].value, first_spot)


def test_adaptive_advantage_without_discount_equals_recourse_value(scenario, rows):
    by_config = {row["config"]: row for row in rows}
    adaptive_advantage = (
        by_config["fixed/no-discount"]["total_cost"]
        - by_config["recourse/no-discount"]["total_cost"]
    )

    fixed = _solve(scenario, recourse=False)
    adaptive = _solve(scenario, recourse=True)
    recourse_value = float(
        np.mean(_per_scenario_costs(fixed) - _per_scenario_costs(adaptive))
    )

    assert recourse_value > 0
    assert adaptive_advantage == pytest.approx(recourse_value, abs=0.05)
    assert decompose(rows)["recourse_value_no_discount"] == pytest.approx(
        recourse_value, abs=0.05
    )


def test_decomposition_adds_up(rows):
    effects = decompose(rows)
    assert effects["contract_value_fixed"] + effects["recourse_value_with_discount"] == (
        pytest.approx(effects["total_gap"], abs=0.02)
    )
    assert effects["recourse_value_no_discount"] + effects["contract_value_recourse"] == (
        pytest.approx(effects["total_gap"], abs=0.02)
    )


def test_adaptive_robust_saving_is_the_contract_discount(rows):
    # The affine adaptive model's saving over the nominal plan disappears once
    # both pay nominal prices, so its headline saving is the discount alone.
    by_config = {row["config"]: row for row in rows}
    assert by_config["adaptive@0.95"]["cost_delta"] < -1000
    assert by_config["adaptive@0.95/no-discount"]["cost_delta"] == pytest.approx(0, abs=1.0)


def test_unserved_demand_counts_people_a_budget_cut_leaves_out(scenario):
    model = BudgetConstrainedModel(scenario, budget=6000)
    assert model.solve() == "optimal"
    solution = extract_solution(model)

    assert solution.nutrient_slack < 1
    expected = (1 - solution.nutrient_slack) * scenario.total_demand
    assert solution.unserved_demand == pytest.approx(expected, rel=1e-3)


def test_unserved_people_counts_a_delivery_shortfall_at_one_node(scenario):
    # Full nutrient coverage, full delivery everywhere except one commodity at
    # the first demand node, which gets half its ration: that node's people
    # are half served, so half of them count as unmet ration.
    ration = np.zeros(len(scenario.commodity_list))
    ration[0] = 500.0
    nutrients = np.array([scenario.get_requirement(n) for n in scenario.nutrient_list])
    people = np.array([scenario.demand_dict[d] for d in scenario.demand_nodes], dtype=float)
    delivery = np.outer(people, ration) / 1000
    delivery[0, 0] *= 0.5

    expected = people[0] * 0.5
    assert unserved_people(scenario, delivery, ration, nutrients) == pytest.approx(
        expected, abs=0.1
    )
    assert unserved_people(scenario, np.outer(people, ration) / 1000, ration, nutrients) == 0.0
