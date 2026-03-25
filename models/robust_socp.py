"""Model 3: Robust SOCP — protect against price uncertainty with ellipsoidal sets."""

import cvxpy as cp
import numpy as np
from scipy.stats import norm as normal_dist

from core.scenario import Scenario
from .base_model import BaseModel


class RobustSOCP(BaseModel):
    """Robust optimization with ellipsoidal uncertainty on procurement costs.

    The robust counterpart adds an SOCP constraint:
        procurement_cost >= nominal_cost + Phi^{-1}(p) * ||sigma_vec||_2

    Where sigma_vec encodes per-item uncertainty from the scenario's
    price_std_fraction, correlation_group, and cross_correlation parameters.
    """

    def __init__(
        self,
        scenario: Scenario,
        robustness_level: float = 0.95,
        budget: float = None,
        fix_slack: float = None,
    ):
        # Don't call super().__init__ yet — we need to override the cost constraint
        self.scenario = scenario
        self.robustness_level = robustness_level
        self.variables = {}
        self.constraints = []
        self.objective = None
        self.problem = None
        self._solved = False

        # Build common structure
        self._build_variables()
        self._build_robust_cost(robustness_level)
        self._build_flow_constraints()
        self._build_nutrition_constraints()
        self._build_diet_constraints()

        # Slack handling
        if fix_slack is not None:
            self.constraints.append(self.variables["nutrient_slack"] == fix_slack)

        # Budget or cost minimization
        if budget is not None:
            self.constraints.append(self._total_cost() <= budget)
            if fix_slack is None:
                self.objective = cp.Maximize(self.variables["nutrient_slack"])
            else:
                self.objective = cp.Minimize(self._total_cost())
        else:
            if fix_slack is None:
                self.constraints.append(self.variables["nutrient_slack"] == 1.0)
            self.objective = cp.Minimize(self._total_cost())

        self.problem = cp.Problem(self.objective, self.constraints)

    def _build_robust_cost(self, robustness_level: float):
        """Build the SOCP robust counterpart for procurement cost."""
        s = self.scenario
        proc = self.variables["procurement"]
        flow = self.variables["flow"]
        trans = self.variables["transportation"]

        # Link transportation to commodity flows
        for (a, b) in s.edge_index:
            self.constraints.append(
                trans[(a, b)] == sum(flow[(a, b, c)] for c in s.commodity_list)
            )

        # Transportation cost
        self.variables["transportation_cost"] = cp.Variable(nonneg=True, name="trans_cost")
        self.constraints.append(
            self.variables["transportation_cost"]
            >= sum(
                s.get_transport_cost(a, b) * trans[(a, b)] for (a, b) in s.edge_index
            )
        )

        # Nominal procurement cost
        nominal_cost = sum(
            s.price_lookup[(n, c)] * proc[(n, c)] for (n, c) in s.procurement_index
        )

        # Procurement cost variable
        self.variables["procurement_cost"] = cp.Variable(nonneg=True, name="proc_cost")

        if robustness_level <= 0.5:
            # No robustness — just nominal
            self.constraints.append(
                self.variables["procurement_cost"] >= nominal_cost
            )
            return

        # Build sigma vector for the SOCP norm term
        kappa = normal_dist.ppf(robustness_level)
        sigma_terms = []

        # Group procurement by correlation group for cross-correlation
        group_items = {}  # correlation_group -> list of (node, commodity) keys
        for (n, c) in s.procurement_index:
            params = s.uncertainty_params.get((n, c), {})
            group = params.get("correlation_group")
            if isinstance(group, str) and group:
                if group not in group_items:
                    group_items[group] = []
                group_items[group].append((n, c))

        for (n, c) in s.procurement_index:
            params = s.uncertainty_params.get((n, c), {})
            std_frac = params.get("price_std_fraction", 0.0)
            group = params.get("correlation_group")
            cross_corr = params.get("cross_correlation", 0.0)

            if np.isnan(std_frac) or std_frac == 0:
                sigma_terms.append(0.0)
                continue

            price = s.price_lookup[(n, c)]
            own_term = std_frac * price * proc[(n, c)]

            # Add the node-level correlation term used in the MIT homework:
            # 0.30 * own + 0.05 * sum(all commodities at node)
            # With scenario data this becomes std_frac * own + cross_corr * group_sum.
            if isinstance(group, str) and group and not np.isnan(cross_corr) and cross_corr > 0:
                cross_term = cross_corr * sum(
                    s.price_lookup[(gn, gc)] * proc[(gn, gc)]
                    for (gn, gc) in group_items.get(group, [])
                )
                sigma_terms.append(own_term + cross_term)
            else:
                sigma_terms.append(own_term)

        # Filter out zero terms and build the norm
        nonzero_terms = [t for t in sigma_terms if not isinstance(t, (int, float)) or t != 0]

        if nonzero_terms:
            sigma_vec = cp.vstack([t if isinstance(t, cp.Expression) else cp.Constant(t) for t in nonzero_terms])
            self.constraints.append(
                self.variables["procurement_cost"]
                >= nominal_cost + kappa * cp.norm(sigma_vec, 2)
            )
        else:
            self.constraints.append(
                self.variables["procurement_cost"] >= nominal_cost
            )

        # Store for reporting
        self._nominal_proc_cost = nominal_cost

    def _build_cost_variables(self):
        """Override: cost variables are built in _build_robust_cost."""
        pass

    def _total_cost(self):
        return self.variables["procurement_cost"] + self.variables["transportation_cost"]
