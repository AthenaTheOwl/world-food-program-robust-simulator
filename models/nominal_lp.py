"""Model 1: Nominal LP — minimize cost with full nutritional coverage."""

import cvxpy as cp

from core.scenario import Scenario
from .base_model import BaseModel


class NominalLP(BaseModel):
    """Minimize total procurement + transportation cost with nutrient_slack = 1.0."""

    def __init__(self, scenario: Scenario):
        super().__init__(scenario)
        # Fix slack to 1.0 (full nutritional coverage)
        self.constraints.append(self.variables["nutrient_slack"] == 1.0)
        self.objective = cp.Minimize(self._total_cost())
        self.problem = cp.Problem(self.objective, self.constraints)
