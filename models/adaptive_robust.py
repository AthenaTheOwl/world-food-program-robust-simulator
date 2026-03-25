"""Model 6: Adaptive (two-stage) robust optimization with affine decision rules."""

import cvxpy as cp
import numpy as np
from scipy.stats import norm as normal_dist

from core.scenario import Scenario
from config import DEFAULT_SOLVER, FALLBACK_SOLVER


class AdaptiveRobustModel:
    """Two-stage robust optimization using affine decision rules.

    First stage (here-and-now): contract decisions — contracted volumes at
    locked-in prices, decided before uncertainty is revealed.

    Second stage (wait-and-see): spot procurement and routing — adjusted after
    prices are revealed. Approximated as affine functions of the uncertain
    parameters (affine decision rules) to keep the problem tractable.

    The affine decision rule approximation:
        procurement_spot[n,c](z) = x0[n,c] + sum_k x_k[n,c] * z_k

    where z is the vector of uncertain price perturbations. This yields a
    single SOCP, solvable with standard convex solvers.
    """

    def __init__(
        self,
        scenario: Scenario,
        robustness_level: float = 0.95,
        contract_discount: float = 0.9,
        max_contract_fraction: float = 0.8,
    ):
        self.scenario = scenario
        self.robustness_level = robustness_level
        self.variables = {}
        self.constraints = []
        self._solved = False

        s = scenario
        kappa = normal_dist.ppf(robustness_level) if robustness_level > 0.5 else 0

        procurement_set = set(s.procurement_index)
        demand_set = set(s.demand_nodes)
        n_uncertain = len(s.procurement_index)

        # === FIRST STAGE: Contract decisions ===
        # Contract volume at each (node, commodity) — locked-in price
        contract = {
            (n, c): cp.Variable(nonneg=True, name=f"contract_{n}_{c}")
            for (n, c) in s.procurement_index
        }
        self.variables["contract"] = contract

        # Contract cost (discounted price — reward for commitment)
        contract_cost = sum(
            contract_discount * s.price_lookup[(n, c)] * contract[(n, c)]
            for (n, c) in s.procurement_index
        )

        # Contract volume cannot exceed a fraction of what we might need
        # (prevents contracting more than can be used)
        for (n, c) in s.procurement_index:
            max_tons = max_contract_fraction * s.total_demand * 0.001  # rough upper bound
            self.constraints.append(contract[(n, c)] <= max_tons)

        # === SECOND STAGE: Spot procurement (affine in uncertainty) ===
        # Nominal spot procurement (constant term of affine rule)
        spot_nominal = {
            (n, c): cp.Variable(nonneg=True, name=f"spot0_{n}_{c}")
            for (n, c) in s.procurement_index
        }
        self.variables["spot_nominal"] = spot_nominal

        # Affine coefficients: how spot procurement reacts to each uncertainty dimension
        # For tractability, use a simplified affine rule where spot procurement
        # at (n,c) depends only on the price perturbation at (n,c) itself
        spot_sensitivity = {
            (n, c): cp.Variable(name=f"spot_sens_{n}_{c}")
            for (n, c) in s.procurement_index
        }
        self.variables["spot_sensitivity"] = spot_sensitivity

        # Total procurement = contract + spot (at nominal)
        total_procurement = {
            (n, c): contract[(n, c)] + spot_nominal[(n, c)]
            for (n, c) in s.procurement_index
        }

        # === Flow and delivery variables (deterministic, based on nominal) ===
        flow = {
            (a, b, c): cp.Variable(nonneg=True)
            for (a, b) in s.edge_index
            for c in s.commodity_list
        }
        self.variables["flow"] = flow

        delivery = {
            (d, c): cp.Variable(nonneg=True)
            for d in s.demand_nodes
            for c in s.commodity_list
        }
        self.variables["delivery"] = delivery

        transportation = {
            (a, b): cp.Variable(nonneg=True)
            for (a, b) in s.edge_index
        }
        self.variables["transportation"] = transportation

        ration_pp = {c: cp.Variable(nonneg=True) for c in s.commodity_list}
        self.variables["ration_pp"] = ration_pp

        nutrients_pp = {n: cp.Variable(nonneg=True) for n in s.nutrient_list}
        self.variables["nutrients_pp"] = nutrients_pp

        # === Transportation constraints ===
        for (a, b) in s.edge_index:
            self.constraints.append(
                transportation[(a, b)] == sum(flow[(a, b, c)] for c in s.commodity_list)
            )

        transportation_cost = sum(
            s.get_transport_cost(a, b) * transportation[(a, b)]
            for (a, b) in s.edge_index
        )

        # === Flow conservation (using total procurement) ===
        for node in s.nodes["node_id"]:
            valid_sources = [a for (a, b) in s.edge_index if b == node]
            valid_sinks = [b for (a, b) in s.edge_index if a == node]

            for commodity in s.commodity_list:
                inflow = sum(flow[(src, node, commodity)] for src in valid_sources)
                outflow = sum(flow[(node, snk, commodity)] for snk in valid_sinks)
                supply = (
                    total_procurement[(node, commodity)]
                    if (node, commodity) in procurement_set
                    else 0
                )
                local_delivery = (
                    delivery[(node, commodity)] if node in demand_set else 0
                )
                self.constraints.append(supply + inflow == outflow + local_delivery)

        # === Nutrition constraints ===
        for nutrient in s.nutrient_list:
            self.constraints.append(
                nutrients_pp[nutrient]
                == 10 * sum(
                    ration_pp[c] * s.nutrition_matrix.get(c, {}).get(nutrient, 0)
                    for c in s.commodity_list
                )
            )
            req = s.get_requirement(nutrient)
            self.constraints.append(nutrients_pp[nutrient] >= req)

        for d in s.demand_nodes:
            demand = s.demand_dict[d]
            for c in s.commodity_list:
                self.constraints.append(1000 * delivery[(d, c)] >= demand * ration_pp[c])

        # === Diet constraints ===
        energy_key = next((n for n in s.nutrient_list if "energy" in n.lower()), None)
        protein_key = next((n for n in s.nutrient_list if "protein" in n.lower()), None)
        fat_key = next((n for n in s.nutrient_list if "fat" in n.lower()), None)

        if energy_key and protein_key and fat_key:
            carbs_pp = cp.Variable(nonneg=True)
            self.constraints.append(
                4 * carbs_pp == nutrients_pp[energy_key] - 4 * nutrients_pp[protein_key] - 9 * nutrients_pp[fat_key]
            )
            self.constraints.append(carbs_pp >= 4 * nutrients_pp[protein_key])
            self.constraints.append(carbs_pp >= 4 * nutrients_pp[fat_key])

        # === Robust spot procurement cost ===
        # Nominal spot cost
        nominal_spot_cost = sum(
            s.price_lookup[(n, c)] * spot_nominal[(n, c)]
            for (n, c) in s.procurement_index
        )

        # Build uncertainty terms for the SOCP constraint
        # The realized spot cost under perturbation z is:
        #   sum_i price_i * (spot_nominal_i + spot_sensitivity_i * z_i) * (1 + sigma_i * z_i)
        # Approximating to first order: nominal + sum_i (sigma_i * price_i * spot_nominal_i) * z_i
        # plus the sensitivity adjustments
        spot_cost_var = cp.Variable(nonneg=True, name="spot_cost")
        self.variables["spot_cost"] = spot_cost_var

        if kappa > 0:
            # Build sigma vector for SOCP
            group_items = {}
            for (n, c) in s.procurement_index:
                params = s.uncertainty_params.get((n, c), {})
                group = params.get("correlation_group")
                if isinstance(group, str) and group:
                    if group not in group_items:
                        group_items[group] = []
                    group_items[group].append((n, c))

            sigma_terms = []
            for (n, c) in s.procurement_index:
                params = s.uncertainty_params.get((n, c), {})
                std_frac = params.get("price_std_fraction", 0.0)
                group = params.get("correlation_group")
                cross_corr = params.get("cross_correlation", 0.0)
                if np.isnan(std_frac) or std_frac == 0:
                    continue

                price = s.price_lookup[(n, c)]
                term = std_frac * price * spot_nominal[(n, c)]
                if isinstance(group, str) and group and not np.isnan(cross_corr) and cross_corr > 0:
                    term += cross_corr * sum(
                        s.price_lookup[(gn, gc)] * spot_nominal[(gn, gc)]
                        for (gn, gc) in group_items.get(group, [])
                    )
                sigma_terms.append(term)

            if sigma_terms:
                sigma_vec = cp.vstack(sigma_terms)
                self.constraints.append(
                    spot_cost_var >= nominal_spot_cost + kappa * cp.norm(sigma_vec, 2)
                )
            else:
                self.constraints.append(spot_cost_var >= nominal_spot_cost)
        else:
            self.constraints.append(spot_cost_var >= nominal_spot_cost)

        # === Total cost ===
        total_cost = contract_cost + spot_cost_var + transportation_cost
        self.variables["total_cost"] = total_cost
        self.variables["contract_cost_expr"] = contract_cost
        self.variables["transportation_cost"] = transportation_cost

        # === Non-negativity of spot under worst-case uncertainty ===
        # Spot procurement must be non-negative even under worst-case z
        # For affine rule: x0 + x_sens * z >= 0 for all z in uncertainty set
        # With ||z||_2 <= kappa: x0 - kappa * |x_sens| >= 0
        if kappa > 0:
            for (n, c) in s.procurement_index:
                self.constraints.append(
                    spot_nominal[(n, c)] >= kappa * cp.abs(spot_sensitivity[(n, c)])
                )

        # Objective
        self.objective = cp.Minimize(total_cost)
        self.problem = cp.Problem(self.objective, self.constraints)

    def solve(self, verbose=False):
        try:
            self.problem.solve(solver=DEFAULT_SOLVER, verbose=verbose)
        except cp.SolverError:
            self.problem.solve(solver=FALLBACK_SOLVER, verbose=verbose)

        if self.problem.status in ("optimal", "optimal_inaccurate"):
            self._solved = True
        return self.problem.status

    @property
    def is_solved(self):
        return self._solved

    def extract_results(self) -> dict:
        """Extract structured results from the solved adaptive model."""
        if not self._solved:
            return {"status": "unsolved"}

        s = self.scenario
        contract = self.variables["contract"]
        spot = self.variables["spot_nominal"]

        # Contract volumes
        contract_volumes = {}
        contract_cost_total = 0
        for (n, c) in s.procurement_index:
            val = float(contract[(n, c)].value or 0)
            if val > 1e-3:
                contract_volumes[(n, c)] = val
                contract_cost_total += 0.9 * s.price_lookup[(n, c)] * val

        # Spot volumes
        spot_volumes = {}
        spot_cost_total = 0
        for (n, c) in s.procurement_index:
            val = float(spot[(n, c)].value or 0)
            if val > 1e-3:
                spot_volumes[(n, c)] = val
                spot_cost_total += s.price_lookup[(n, c)] * val

        # Transportation
        trans_cost = sum(
            s.get_transport_cost(a, b) * float(self.variables["transportation"][(a, b)].value or 0)
            for (a, b) in s.edge_index
        )

        total = contract_cost_total + float(self.variables["spot_cost"].value or 0) + trans_cost

        # Ration
        ration_pp = {
            c: float(self.variables["ration_pp"][c].value or 0)
            for c in s.commodity_list
            if float(self.variables["ration_pp"][c].value or 0) > 1e-4
        }

        return {
            "status": self.problem.status,
            "total_cost": round(total, 2),
            "contract_cost": round(contract_cost_total, 2),
            "spot_cost": round(float(self.variables["spot_cost"].value or 0), 2),
            "transportation_cost": round(trans_cost, 2),
            "contract_volumes": contract_volumes,
            "spot_volumes": spot_volumes,
            "contract_fraction": round(
                contract_cost_total / total if total > 0 else 0, 3
            ),
            "num_contracts": len(contract_volumes),
            "num_spot_purchases": len(spot_volumes),
            "ration_pp": ration_pp,
        }
