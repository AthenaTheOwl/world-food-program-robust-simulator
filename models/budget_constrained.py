"""Model 2: Budget-constrained — maximize nutrition coverage under a fixed budget."""

import cvxpy as cp

from core.scenario import Scenario
from .base_model import BaseModel


class BudgetConstrainedModel(BaseModel):
    """Maximize nutrient_slack subject to total cost <= budget."""

    def __init__(self, scenario: Scenario, budget: float):
        super().__init__(scenario)
        self.budget = budget

        # Budget constraint
        self.constraints.append(self._total_cost() <= budget)

        # Maximize nutrition slack
        self.objective = cp.Maximize(self.variables["nutrient_slack"])
        self.problem = cp.Problem(self.objective, self.constraints)
