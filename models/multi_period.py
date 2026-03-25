"""Model 5: Multi-period planning with inventory, spoilage, and lead times."""

import cvxpy as cp
import numpy as np

from core.scenario import Scenario
from config import DEFAULT_SOLVER, FALLBACK_SOLVER


class MultiPeriodModel:
    """Multi-period food relief optimization with inventory management.

    Extends the single-period model across T time periods. New features:
    - Inventory carry-over between periods
    - Spoilage based on commodity shelf life
    - Lead times on transportation edges
    - Time-varying demand trajectories
    - Holding costs for stored inventory

    Decision variables per period t:
        procurement[n, c, t] — tons procured
        flow[a, b, c, t] — commodity flow (arrives at t + lead_time)
        delivery[d, c, t] — tons delivered to demand
        inventory[n, c, t] — stored tons at end of period
        ration_pp[c, t] — kg per person per day in period t
    """

    def __init__(
        self,
        scenario: Scenario,
        num_periods: int = 7,
        demand_trajectory: np.ndarray = None,
        holding_cost_per_ton: float = 10.0,
        initial_inventory: dict = None,
    ):
        self.scenario = scenario
        self.num_periods = num_periods
        self.holding_cost = holding_cost_per_ton
        self.variables = {}
        self.constraints = []
        self._solved = False

        s = scenario
        T = num_periods
        commodities = s.commodity_list
        nutrients = s.nutrient_list

        # Demand trajectory: (num_periods, num_demand_nodes)
        if demand_trajectory is None:
            # Constant demand across all periods
            self.demand_trajectory = np.tile(
                [s.demand_dict.get(d, 0) for d in s.demand_nodes], (T, 1)
            )
        else:
            self.demand_trajectory = demand_trajectory

        # Spoilage rates from shelf life
        self.spoilage_rates = {}
        for _, row in s.commodities.iterrows():
            cid = row["commodity_id"]
            shelf_life = row.get("shelf_life_days", np.inf)
            if np.isfinite(shelf_life) and shelf_life > 0:
                self.spoilage_rates[cid] = 1 - np.exp(-1.0 / shelf_life)
            else:
                self.spoilage_rates[cid] = 0.0

        # Lead times from edges
        self.lead_times = {}
        for _, row in s.edges.iterrows():
            lt = row.get("lead_time_days", 0)
            self.lead_times[(row["source"], row["target"])] = int(lt) if np.isfinite(lt) else 0

        # --- Build variables ---
        procurement_set = set(s.procurement_index)

        # Procurement per period
        self.variables["procurement"] = {
            (n, c, t): cp.Variable(nonneg=True)
            for (n, c) in s.procurement_index
            for t in range(T)
        }

        # Flow per period (indexed by departure time)
        self.variables["flow"] = {
            (a, b, c, t): cp.Variable(nonneg=True)
            for (a, b) in s.edge_index
            for c in commodities
            for t in range(T)
        }

        # Delivery per period
        self.variables["delivery"] = {
            (d, c, t): cp.Variable(nonneg=True)
            for d in s.demand_nodes
            for c in commodities
            for t in range(T)
        }

        # Inventory at storage-capable nodes (supply and transshipment nodes)
        storage_nodes = list(set(s.supply_nodes) | set(s.demand_nodes))
        self.storage_nodes = storage_nodes
        self.variables["inventory"] = {
            (n, c, t): cp.Variable(nonneg=True)
            for n in storage_nodes
            for c in commodities
            for t in range(T)
        }

        # Ration per person per period
        self.variables["ration_pp"] = {
            (c, t): cp.Variable(nonneg=True)
            for c in commodities
            for t in range(T)
        }

        # Nutrients per person per period
        self.variables["nutrients_pp"] = {
            (n, t): cp.Variable(nonneg=True)
            for n in nutrients
            for t in range(T)
        }

        # --- Build constraints ---
        proc = self.variables["procurement"]
        flow = self.variables["flow"]
        delivery = self.variables["delivery"]
        inv = self.variables["inventory"]
        ration = self.variables["ration_pp"]
        nutr_pp = self.variables["nutrients_pp"]

        # Initial inventory
        init_inv = initial_inventory or {}

        for t in range(T):
            # Flow conservation with inventory at each node
            for node in s.nodes["node_id"].tolist():
                valid_sources = [a for (a, b) in s.edge_index if b == node]
                valid_sinks = [b for (a, b) in s.edge_index if a == node]

                for c in commodities:
                    # Inflow: arrivals from flows that departed earlier (accounting for lead time)
                    inflow = 0
                    for src in valid_sources:
                        lt = self.lead_times.get((src, node), 0)
                        depart_t = t - lt
                        if 0 <= depart_t < T:
                            inflow += flow[(src, node, c, depart_t)]

                    # Outflow: flows departing this period
                    outflow = sum(flow[(node, snk, c, t)] for snk in valid_sinks)

                    if node in storage_nodes:
                        # Inventory balance
                        prev_inv = inv[(node, c, t - 1)] if t > 0 else init_inv.get((node, c), 0)
                        spoilage = self.spoilage_rates.get(c, 0) * prev_inv if t > 0 else 0

                        supply = proc[(node, c, t)] if (node, c) in procurement_set else 0

                        if node in s.demand_nodes:
                            # Demand node with possible supply
                            self.constraints.append(
                                inv[(node, c, t)] == prev_inv - spoilage + supply + inflow - outflow - delivery[(node, c, t)]
                            )
                        else:
                            # Supply/transit node
                            self.constraints.append(
                                inv[(node, c, t)] == prev_inv - spoilage + supply + inflow - outflow
                            )
                    else:
                        # Non-storage node: pure transit, no inventory
                        if (node, c) in procurement_set:
                            self.constraints.append(proc[(node, c, t)] + inflow == outflow)
                        elif node in s.demand_nodes:
                            self.constraints.append(delivery[(node, c, t)] == inflow - outflow)
                        else:
                            self.constraints.append(inflow == outflow)

            # Nutrition constraints per period
            for nutrient in nutrients:
                self.constraints.append(
                    nutr_pp[(nutrient, t)]
                    == 10 * sum(
                        ration[(c, t)] * s.nutrition_matrix.get(c, {}).get(nutrient, 0)
                        for c in commodities
                    )
                )
                req = s.get_requirement(nutrient)
                self.constraints.append(nutr_pp[(nutrient, t)] >= req)

            # Demand satisfaction per period
            for di, d in enumerate(s.demand_nodes):
                demand_t = self.demand_trajectory[t, di]
                for c in commodities:
                    self.constraints.append(
                        1000 * delivery[(d, c, t)] >= demand_t * ration[(c, t)]
                    )

            # Diet constraints per period
            energy_key = next((n for n in nutrients if "energy" in n.lower()), None)
            protein_key = next((n for n in nutrients if "protein" in n.lower()), None)
            fat_key = next((n for n in nutrients if "fat" in n.lower()), None)

            if energy_key and protein_key and fat_key:
                carbs_t = cp.Variable(nonneg=True)
                self.constraints.append(
                    4 * carbs_t == nutr_pp[(energy_key, t)] - 4 * nutr_pp[(protein_key, t)] - 9 * nutr_pp[(fat_key, t)]
                )
                self.constraints.append(carbs_t >= 4 * nutr_pp[(protein_key, t)])
                self.constraints.append(carbs_t >= 4 * nutr_pp[(fat_key, t)])

        # --- Cost computation ---
        procurement_cost = sum(
            s.price_lookup[(n, c)] * proc[(n, c, t)]
            for (n, c) in s.procurement_index
            for t in range(T)
        )

        transportation_cost = sum(
            s.get_transport_cost(a, b) * sum(flow[(a, b, c, t)] for c in commodities)
            for (a, b) in s.edge_index
            for t in range(T)
        )

        holding_cost_total = holding_cost_per_ton * sum(
            inv[(n, c, t)]
            for n in storage_nodes
            for c in commodities
            for t in range(T)
        )

        self.variables["procurement_cost"] = procurement_cost
        self.variables["transportation_cost"] = transportation_cost
        self.variables["holding_cost"] = holding_cost_total
        self.total_cost_expr = procurement_cost + transportation_cost + holding_cost_total

        # Objective: minimize total cost
        self.objective = cp.Minimize(self.total_cost_expr)
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

    def extract_period_results(self) -> list[dict]:
        """Extract per-period metrics from the solved model."""
        if not self._solved:
            return []

        s = self.scenario
        T = self.num_periods
        results = []

        for t in range(T):
            # Procurement cost for this period
            proc_cost_t = sum(
                s.price_lookup[(n, c)] * float(self.variables["procurement"][(n, c, t)].value or 0)
                for (n, c) in s.procurement_index
            )

            # Transportation cost for this period
            trans_cost_t = sum(
                s.get_transport_cost(a, b) * sum(
                    float(self.variables["flow"][(a, b, c, t)].value or 0)
                    for c in s.commodity_list
                )
                for (a, b) in s.edge_index
            )

            # Total delivery
            total_delivery_t = sum(
                float(self.variables["delivery"][(d, c, t)].value or 0)
                for d in s.demand_nodes
                for c in s.commodity_list
            )

            # Total inventory
            total_inv_t = sum(
                float(self.variables["inventory"][(n, c, t)].value or 0)
                for n in self.storage_nodes
                for c in s.commodity_list
            )

            # Ration
            ration_t = {
                c: float(self.variables["ration_pp"][(c, t)].value or 0)
                for c in s.commodity_list
            }
            total_ration_t = sum(v for v in ration_t.values() if v > 1e-6)

            results.append({
                "period": t + 1,
                "procurement_cost": round(proc_cost_t, 2),
                "transportation_cost": round(trans_cost_t, 2),
                "total_cost": round(proc_cost_t + trans_cost_t, 2),
                "total_delivery_tons": round(total_delivery_t, 3),
                "total_inventory_tons": round(total_inv_t, 3),
                "total_ration_kg_pp": round(total_ration_t, 4),
                "demand": self.demand_trajectory[t].sum(),
            })

        return results
