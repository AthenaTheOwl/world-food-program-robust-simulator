"""Base optimization model: builds common cvxpy variables and constraints for any Scenario."""

import cvxpy as cp
import numpy as np
from scipy.stats import norm

from core.scenario import Scenario
from config import DEFAULT_SOLVER, FALLBACK_SOLVER


class BaseModel:
    """Builds the common multi-commodity flow structure shared by all models.

    Decision variables:
        procurement[(node, commodity)] — tons procured
        flow[(source, target, commodity)] — commodity flow on each edge
        delivery[(demand_node, commodity)] — tons delivered
        transportation[(source, target)] — total tons on each edge
        ration_pp[commodity_idx] — kg per person per day
        nutrients_pp[nutrient_idx] — nutrient amount per person
        nutrient_slack — scalar multiplier on nutritional requirements
        procurement_cost — total procurement cost variable
        transportation_cost — total transportation cost variable
    """

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.variables = {}
        self.constraints = []
        self.objective = None
        self.problem = None
        self._solved = False

        self._build_variables()
        self._build_cost_variables()
        self._build_flow_constraints()
        self._build_nutrition_constraints()
        self._build_diet_constraints()

    def _build_variables(self):
        s = self.scenario

        # Procurement: one variable per (node, commodity) procurement link
        self.variables["procurement"] = {
            (n, c): cp.Variable(nonneg=True, name=f"proc_{n}_{c}")
            for (n, c) in s.procurement_index
        }

        # Flow: one variable per (source, target, commodity) on each edge
        self.variables["flow"] = {
            (a, b, c): cp.Variable(nonneg=True, name=f"flow_{a}_{b}_{c}")
            for (a, b) in s.edge_index
            for c in s.commodity_list
        }

        # Delivery: one variable per (demand_node, commodity)
        self.variables["delivery"] = {
            (d, c): cp.Variable(nonneg=True, name=f"del_{d}_{c}")
            for d in s.demand_nodes
            for c in s.commodity_list
        }

        # Transportation: total tons on each edge
        self.variables["transportation"] = {
            (a, b): cp.Variable(nonneg=True, name=f"trans_{a}_{b}")
            for (a, b) in s.edge_index
        }

        # Ration per person (kg/person/day) — one per commodity
        self.variables["ration_pp"] = {
            c: cp.Variable(nonneg=True, name=f"ration_{c}")
            for c in s.commodity_list
        }

        # Nutrients per person — one per nutrient
        self.variables["nutrients_pp"] = {
            n: cp.Variable(nonneg=True, name=f"nutr_{n}")
            for n in s.nutrient_list
        }

        # Nutrient slack (multiplier on requirements)
        self.variables["nutrient_slack"] = cp.Variable(nonneg=True, name="slack")

    def _build_cost_variables(self):
        s = self.scenario
        proc = self.variables["procurement"]
        trans = self.variables["transportation"]
        flow = self.variables["flow"]

        # Link transportation to total commodity flow on each edge
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

        # Nominal procurement cost (may be overridden by robust model)
        self._nominal_proc_cost = sum(
            s.price_lookup[(n, c)] * proc[(n, c)] for (n, c) in s.procurement_index
        )

        # Default: procurement_cost equals nominal cost
        self.variables["procurement_cost"] = cp.Variable(nonneg=True, name="proc_cost")
        self.constraints.append(
            self.variables["procurement_cost"] >= self._nominal_proc_cost
        )

    def _build_flow_constraints(self):
        """Flow conservation at every node for every commodity."""
        s = self.scenario
        proc = self.variables["procurement"]
        flow = self.variables["flow"]
        delivery = self.variables["delivery"]

        procurement_set = set(s.procurement_index)
        demand_set = set(s.demand_nodes)

        for node in s.nodes["node_id"]:
            # Find valid source edges (into this node) and sink edges (out of this node)
            valid_sources = [a for (a, b) in s.edge_index if b == node]
            valid_sinks = [b for (a, b) in s.edge_index if a == node]

            for commodity in s.commodity_list:
                inflow = sum(flow[(src, node, commodity)] for src in valid_sources)
                outflow = sum(flow[(node, snk, commodity)] for snk in valid_sinks)
                supply = proc[(node, commodity)] if (node, commodity) in procurement_set else 0
                local_delivery = (
                    delivery[(node, commodity)] if node in demand_set else 0
                )

                # Unified conservation law. This handles pure suppliers, pure demand
                # nodes, and hybrid local markets that can both procure and serve demand.
                self.constraints.append(supply + inflow == outflow + local_delivery)

    def _build_nutrition_constraints(self):
        """Ensure rations meet nutritional requirements."""
        s = self.scenario
        ration = self.variables["ration_pp"]
        nutrients = self.variables["nutrients_pp"]
        slack = self.variables["nutrient_slack"]
        delivery = self.variables["delivery"]

        # Nutrients per person = 10 * sum(ration[c] * nutrition[c][n])
        # Factor of 10: nutrition data is per 100g, rations are in kg
        for nutrient in s.nutrient_list:
            self.constraints.append(
                nutrients[nutrient]
                == 10
                * sum(
                    ration[c] * s.nutrition_matrix.get(c, {}).get(nutrient, 0)
                    for c in s.commodity_list
                )
            )
            # Must meet requirement * slack
            req = s.get_requirement(nutrient)
            self.constraints.append(nutrients[nutrient] >= slack * req)

        # Delivery must satisfy demand: 1000 * delivery[d,c] >= demand[d] * ration_pp[c]
        # Factor of 1000: ration is kg/person, delivery is tons
        for d in s.demand_nodes:
            demand_persons = s.demand_dict[d]
            for c in s.commodity_list:
                self.constraints.append(
                    1000 * delivery[(d, c)] >= demand_persons * ration[c]
                )

    def _build_diet_constraints(self):
        """Build diet balance constraints (e.g. carb:protein ratio >= 4:1)."""
        s = self.scenario
        nutrients = self.variables["nutrients_pp"]

        if s.diet_constraints.empty:
            return

        # For the standard Syria case, we handle the known constraint patterns
        # The energy balance: 4*carbs = Energy - 4*Protein - 9*Fat
        # Then: carbs >= 4*Protein, carbs >= 4*Fat
        energy_key = None
        protein_key = None
        fat_key = None
        for n in s.nutrient_list:
            nl = n.lower()
            if "energy" in nl:
                energy_key = n
            elif "protein" in nl:
                protein_key = n
            elif "fat" in nl:
                fat_key = n

        if energy_key and protein_key and fat_key:
            carbs_pp = cp.Variable(nonneg=True, name="carbs_pp")
            self.variables["carbs_pp"] = carbs_pp
            self.constraints.append(
                4 * carbs_pp
                == nutrients[energy_key]
                - 4 * nutrients[protein_key]
                - 9 * nutrients[fat_key]
            )

            for _, row in s.diet_constraints.iterrows():
                expr = row["expression"]
                if "protein" in expr.lower() and ">=" in expr:
                    self.constraints.append(carbs_pp >= 4 * nutrients[protein_key])
                elif "fat" in expr.lower() and ">=" in expr:
                    self.constraints.append(carbs_pp >= 4 * nutrients[fat_key])

    def _total_cost(self):
        return self.variables["procurement_cost"] + self.variables["transportation_cost"]

    def solve(self, solver=None, verbose=False):
        """Solve the optimization problem."""
        if self.problem is None:
            raise RuntimeError("No objective set. Use a subclass (NominalLP, etc.).")

        solve_kwargs = {"verbose": verbose}
        target_solver = solver or DEFAULT_SOLVER

        try:
            self.problem.solve(solver=target_solver, **solve_kwargs)
        except cp.SolverError:
            # Fallback to SCS
            self.problem.solve(solver=FALLBACK_SOLVER, **solve_kwargs)

        if self.problem.status in ("optimal", "optimal_inaccurate"):
            self._solved = True
        return self.problem.status

    @property
    def is_solved(self):
        return self._solved

    @property
    def optimal_value(self):
        return self.problem.value if self._solved else None
