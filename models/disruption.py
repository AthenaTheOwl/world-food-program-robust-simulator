"""Model 4: Disruption scenarios — parameterized node/edge failures."""

import cvxpy as cp
import numpy as np

from core.scenario import Scenario
from .base_model import BaseModel


class DisruptionModel(BaseModel):
    """Optimization model with parameterized capacity constraints for disruption analysis.

    Uses cp.Parameter for edge and procurement capacities so the problem is
    compiled once and can be re-solved rapidly with different disruption configs.
    """

    def __init__(self, scenario: Scenario, budget: float = None):
        # Build base model first
        super().__init__(scenario)

        # Add capacity parameters for edges
        self.edge_capacities = {}
        for (a, b) in scenario.edge_index:
            cap = cp.Parameter(nonneg=True, value=1e9, name=f"cap_{a}_{b}")
            self.edge_capacities[(a, b)] = cap
            self.constraints.append(self.variables["transportation"][(a, b)] <= cap)

        # Add capacity parameters for procurement
        self.procurement_capacities = {}
        for (n, c) in scenario.procurement_index:
            cap = cp.Parameter(nonneg=True, value=1e9, name=f"pcap_{n}_{c}")
            self.procurement_capacities[(n, c)] = cap
            self.constraints.append(self.variables["procurement"][(n, c)] <= cap)

        # Demand multiplier (for demand surges)
        self.demand_multipliers = {}
        # Note: demand is already baked into constraints, so we'd need to rebuild
        # For now, disruptions focus on supply-side (edges and procurement)

        # Nutrient slack is free (may not be able to meet full requirements under disruption)
        # No slack constraint — let the solver find the best possible

        # Slack upper bound
        self.constraints.append(self.variables["nutrient_slack"] <= 1.0)

        if budget is not None:
            self.constraints.append(self._total_cost() <= budget)
            # With budget: maximize how many people we can feed
            self.objective = cp.Maximize(self.variables["nutrient_slack"])
        else:
            # Without budget: try to meet full nutrition at minimum cost
            # Fix slack to 1.0 — if infeasible, the solver will report it
            self.constraints.append(self.variables["nutrient_slack"] == 1.0)
            self.objective = cp.Minimize(self._total_cost())

        self.problem = cp.Problem(self.objective, self.constraints)

    def reset_disruptions(self):
        """Reset all capacities to unlimited."""
        for cap in self.edge_capacities.values():
            cap.value = 1e9
        for cap in self.procurement_capacities.values():
            cap.value = 1e9

    def disable_edge(self, source: str, target: str):
        """Disable a transportation route."""
        key = (source, target)
        if key in self.edge_capacities:
            self.edge_capacities[key].value = 0.0

    def disable_node(self, node_id: str):
        """Disable all edges and procurement at a node."""
        # Disable all edges from/to this node
        for (a, b), cap in self.edge_capacities.items():
            if a == node_id or b == node_id:
                cap.value = 0.0
        # Disable all procurement at this node
        for (n, c), cap in self.procurement_capacities.items():
            if n == node_id:
                cap.value = 0.0

    def reduce_edge_capacity(self, source: str, target: str, fraction: float):
        """Reduce edge capacity to a fraction of unlimited (0 = disabled, 1 = full)."""
        key = (source, target)
        if key in self.edge_capacities:
            self.edge_capacities[key].value = fraction * 1e9

    def apply_disruptions(
        self,
        disabled_edges: list[tuple[str, str]] = None,
        disabled_nodes: list[str] = None,
        reduced_edges: dict = None,  # {(src, tgt): fraction}
    ):
        """Apply a set of disruptions and re-solve."""
        self.reset_disruptions()

        for edge in (disabled_edges or []):
            self.disable_edge(*edge)

        for node in (disabled_nodes or []):
            self.disable_node(node)

        for edge, fraction in (reduced_edges or {}).items():
            self.reduce_edge_capacity(*edge, fraction)

        return self.solve()
