from pathlib import Path

import pytest

from core.scenario import Scenario
from models.adaptive_robust import AdaptiveRobustModel

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "data" / "examples" / "syria_wfp"


@pytest.fixture(scope="module")
def scenario():
    return Scenario.load(SCENARIO_DIR)


@pytest.mark.parametrize("contract_discount", [0.9, 1.0])
def test_adaptive_reported_cost_uses_configured_discount(scenario, contract_discount):
    model = AdaptiveRobustModel(
        scenario, robustness_level=0.95, contract_discount=contract_discount
    )
    assert model.solve() == "optimal"

    results = model.extract_results()
    assert results["total_cost"] == pytest.approx(model.problem.value, abs=1.0)
