import unittest
from pathlib import Path

from core.scenario import Scenario
from models.nominal_lp import NominalLP
from models.solver_utils import extract_solution


class HybridDemandNodeTests(unittest.TestCase):
    def test_hybrid_nodes_consume_their_local_ration(self):
        scenario_dir = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "examples"
            / "syria_wfp"
        )
        scenario = Scenario.load(scenario_dir)

        model = NominalLP(scenario)
        status = model.solve()
        self.assertIn(status, {"optimal", "optimal_inaccurate"})

        solution = extract_solution(model, robustness_level=0.5)
        total_ration_kg = sum(solution.ration_pp.values())

        hybrid_nodes = ["Hassakeh", "Dara", "Dayr_Az_Zor", "Qamishli"]
        for node in hybrid_nodes:
            delivered_tons = sum(
                solution.delivery.get((node, commodity), 0.0)
                for commodity in scenario.commodity_list
            )
            expected_tons = scenario.demand_dict[node] * total_ration_kg / 1000
            self.assertAlmostEqual(delivered_tons, expected_tons, delta=0.05)


if __name__ == "__main__":
    unittest.main()
