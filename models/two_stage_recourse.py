"""Finite-scenario two-stage stochastic recourse model (vectorized).

Stage 1 (here-and-now): Decide contract procurement volumes at discounted prices
    before price uncertainty is revealed.

Stage 2 (wait-and-see): For each sampled price scenario, decide spot procurement
    volumes, routing, and delivery at the realized prices.

The objective minimizes: contract_cost + (1/S) * sum_s spot_cost_s + transport_cost_s

This is a proper extensive-form stochastic program — not an approximation via
affine decision rules. Each scenario gets its own second-stage variables, so the
model grows linearly with the number of scenarios but gives exact recourse.

All variables are vectorized (cp.Variable with shape) and constraints use matrix
operations to minimize CVXPY expression tree depth.
"""

import cvxpy as cp
import numpy as np
from scipy import sparse

from core.scenario import Scenario
from simulation.monte_carlo import generate_price_scenarios
from config import DEFAULT_SOLVER, FALLBACK_SOLVER


class TwoStageRecourseModel:
    """Finite-scenario two-stage stochastic program with full recourse.

    Parameters
    ----------
    scenario : Scenario
        The food relief scenario.
    n_scenarios : int
        Number of price scenarios to sample. More = better approximation, slower.
    contract_discount : float
        Fraction of nominal price for contract purchases (e.g. 0.9 = 10% off).
    max_contract_fraction : float
        Max fraction of estimated total need that can be contracted.
    seed : int
        RNG seed for reproducible scenario generation.
    """

    def __init__(
        self,
        scenario: Scenario,
        n_scenarios: int = 20,
        contract_discount: float = 0.90,
        max_contract_fraction: float = 0.8,
        seed: int = 42,
    ):
        self.scenario = scenario
        self.n_scenarios = n_scenarios
        self.contract_discount = contract_discount
        self._solved = False

        s = scenario
        S = n_scenarios
        commodities = s.commodity_list

        # ── Dimension constants ──
        P = len(s.procurement_index)
        E = len(s.edge_index)
        C = len(commodities)
        D = len(s.demand_nodes)
        Nn = len(s.nodes)
        K = len(s.nutrient_list)

        self._dims = {"P": P, "E": E, "C": C, "D": D, "Nn": Nn, "K": K}

        # ── Index mappings ──
        node_list = s.nodes["node_id"].tolist()
        node_idx = {n: i for i, n in enumerate(node_list)}
        comm_idx = {c: i for i, c in enumerate(commodities)}

        # ── Precompute constant vectors and matrices ──

        # Contract price vector (P,)
        contract_prices = np.array([
            contract_discount * s.price_lookup[(n, c)]
            for (n, c) in s.procurement_index
        ])

        # Transport cost vector (E,)
        transport_cost_vec = np.array([
            s.get_transport_cost(a, b) for (a, b) in s.edge_index
        ])

        # Node-edge incidence: A_net = A_in - A_out, shape (Nn, E)
        # A_net[n, e] = +1 if edge e enters node n, -1 if it leaves
        rows_in, rows_out, cols_in, cols_out = [], [], [], []
        for ei, (a, b) in enumerate(s.edge_index):
            rows_out.append(node_idx[a]); cols_out.append(ei)
            rows_in.append(node_idx[b]); cols_in.append(ei)

        A_in_sp = sparse.csr_matrix(
            (np.ones(E), (rows_in, cols_in)), shape=(Nn, E)
        )
        A_out_sp = sparse.csr_matrix(
            (np.ones(E), (rows_out, cols_out)), shape=(Nn, E)
        )
        A_net = (A_in_sp - A_out_sp).toarray()  # dense (Nn, E) for CVXPY

        # Supply scatter: maps procurement vector (P,) to (Nn, C) in column-major
        # flat index = ni + ci * Nn (column-major for cp.reshape)
        sup_rows, sup_cols = [], []
        for pi, (n, c) in enumerate(s.procurement_index):
            ni, ci = node_idx[n], comm_idx[c]
            sup_rows.append(ni + ci * Nn)
            sup_cols.append(pi)
        supply_scatter = sparse.csr_matrix(
            (np.ones(P), (sup_rows, sup_cols)), shape=(Nn * C, P)
        ).toarray()

        # Delivery scatter: maps delivery (D, C) flat col-major to (Nn, C) flat col-major
        demand_idx_map = {d: i for i, d in enumerate(s.demand_nodes)}
        del_rows, del_cols = [], []
        for d in s.demand_nodes:
            ni = node_idx[d]
            di = demand_idx_map[d]
            for ci in range(C):
                del_rows.append(ni + ci * Nn)       # target in (Nn, C) col-major
                del_cols.append(di + ci * D)         # source in (D, C) col-major
        delivery_scatter = sparse.csr_matrix(
            (np.ones(len(del_rows)), (del_rows, del_cols)), shape=(Nn * C, D * C)
        ).toarray()

        # Nutrition matrix: (K, C)
        nutr_matrix = np.zeros((K, C))
        for ki, nutrient in enumerate(s.nutrient_list):
            for ci, c in enumerate(commodities):
                nutr_matrix[ki, ci] = s.nutrition_matrix.get(c, {}).get(nutrient, 0)

        # Nutrient requirements: (K,)
        nutr_req = np.array([s.get_requirement(n) for n in s.nutrient_list])

        # Demand vector: (D,)
        demand_vec = np.array([s.demand_dict[d] for d in s.demand_nodes])

        # Diet constraint indices
        energy_idx = protein_idx = fat_idx = None
        for ki, n in enumerate(s.nutrient_list):
            nl = n.lower()
            if "energy" in nl:
                energy_idx = ki
            elif "protein" in nl:
                protein_idx = ki
            elif "fat" in nl:
                fat_idx = ki
        has_diet = energy_idx is not None and protein_idx is not None and fat_idx is not None

        # Generate price scenarios: (S, P)
        self.price_scenarios = generate_price_scenarios(s, S, seed=seed)

        # ── FIRST STAGE: contract vector (P,) ──
        contract = cp.Variable(P, nonneg=True, name="contract")
        contract_cost = contract_prices @ contract

        max_tons = max_contract_fraction * s.total_demand * 0.001
        constraints = [contract <= max_tons]

        # ── SECOND STAGE: per-scenario vectorized variables ──
        self._scenario_vars = []
        scenario_cost_exprs = []

        for si in range(S):
            prices_s = self.price_scenarios[si]  # (P,)

            spot_s = cp.Variable(P, nonneg=True, name=f"spot_{si}")
            flow_s = cp.Variable((E, C), nonneg=True, name=f"flow_{si}")
            delivery_s = cp.Variable((D, C), nonneg=True, name=f"del_{si}")
            ration_s = cp.Variable(C, nonneg=True, name=f"rat_{si}")
            nutrients_s = cp.Variable(K, nonneg=True, name=f"nutr_{si}")

            # Transport = row-sum of flow: (E,)
            transport_s = cp.sum(flow_s, axis=1)

            # ── Flow conservation (single matrix constraint) ──
            # For each commodity c (column): A_net @ flow[:, c] is net inflow at each node
            # net_flow = A_net @ flow_s  → (Nn, C)
            net_flow = A_net @ flow_s

            # Supply: scatter (contract + spot) into (Nn, C)
            total_proc = contract + spot_s  # (P,)
            supply_flat = supply_scatter @ total_proc  # (Nn*C,) col-major
            supply_mat = cp.reshape(supply_flat, (Nn, C), order='F')

            # Delivery: scatter delivery_s (D, C) into (Nn, C)
            del_flat = delivery_scatter @ cp.vec(delivery_s, order='F')  # (Nn*C,) col-major
            delivery_mat = cp.reshape(del_flat, (Nn, C), order='F')

            # supply + net_inflow == delivery  (at every node, every commodity)
            constraints.append(supply_mat + net_flow == delivery_mat)

            # ── Nutrition: nutrients = 10 * nutr_matrix @ ration ──
            constraints.append(nutrients_s == 10 * (nutr_matrix @ ration_s))
            constraints.append(nutrients_s >= nutr_req)

            # ── Demand satisfaction: 1000 * delivery[d,c] >= demand[d] * ration[c] ──
            # demand_outer = demand_vec (D,1) @ ration_s (1,C) → (D, C)
            demand_outer = demand_vec.reshape(-1, 1) @ cp.reshape(ration_s, (1, C), order='F')
            constraints.append(1000 * delivery_s >= demand_outer)

            # ── Diet constraints ──
            if has_diet:
                carbs_s = cp.Variable(nonneg=True, name=f"carbs_{si}")
                constraints.append(
                    4 * carbs_s == nutrients_s[energy_idx]
                    - 4 * nutrients_s[protein_idx]
                    - 9 * nutrients_s[fat_idx]
                )
                constraints.append(carbs_s >= 4 * nutrients_s[protein_idx])
                constraints.append(carbs_s >= 4 * nutrients_s[fat_idx])

            # ── Scenario cost (two dot products) ──
            spot_cost_s = prices_s @ spot_s
            transport_cost_s = transport_cost_vec @ transport_s
            scenario_cost_exprs.append(spot_cost_s + transport_cost_s)

            self._scenario_vars.append({
                "spot": spot_s,
                "flow": flow_s,
                "delivery": delivery_s,
                "transport": transport_s,
                "ration": ration_s,
                "nutrients": nutrients_s,
            })

        # ── OBJECTIVE: contract cost + expected recourse ──
        expected_recourse = (1.0 / S) * cp.sum(cp.hstack(scenario_cost_exprs))
        total_cost = contract_cost + expected_recourse

        self.constraints = constraints
        self.objective = cp.Minimize(total_cost)
        self.problem = cp.Problem(self.objective, constraints)

        # Store references for extraction
        self._contract = contract
        self._contract_cost_expr = contract_cost
        self._scenario_cost_exprs = scenario_cost_exprs

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
        """Extract structured results."""
        if not self._solved:
            return {"status": "unsolved"}

        s = self.scenario
        S = self.n_scenarios
        P = self._dims["P"]

        # Contract volumes
        contract_vals = np.maximum(self._contract.value, 0)
        contract_volumes = {}
        contract_cost_total = 0.0
        for pi, (n, c) in enumerate(s.procurement_index):
            val = float(contract_vals[pi])
            if val > 1e-3:
                contract_volumes[(n, c)] = round(val, 4)
                contract_cost_total += self.contract_discount * s.price_lookup[(n, c)] * val

        # Per-scenario results
        scenario_results = []
        for si in range(S):
            sv = self._scenario_vars[si]
            spot_vals = np.maximum(sv["spot"].value, 0)

            spot_total = float(self.price_scenarios[si] @ spot_vals)

            transport_vals = np.maximum(sv["transport"].value, 0)
            trans_total = float(np.array([
                s.get_transport_cost(a, b) for (a, b) in s.edge_index
            ]) @ transport_vals)

            scenario_results.append({
                "scenario": si,
                "spot_cost": round(spot_total, 2),
                "transport_cost": round(trans_total, 2),
                "recourse_cost": round(spot_total + trans_total, 2),
            })

        avg_recourse = float(np.mean([r["recourse_cost"] for r in scenario_results]))
        total = contract_cost_total + avg_recourse

        # Average ration across scenarios
        ration_pp = {}
        for ci, c in enumerate(self.scenario.commodity_list):
            vals = [float(self._scenario_vars[si]["ration"].value[ci]) for si in range(S)]
            avg = float(np.mean(vals))
            if avg > 1e-4:
                ration_pp[c] = round(avg, 4)

        return {
            "status": self.problem.status,
            "total_cost": round(total, 2),
            "contract_cost": round(contract_cost_total, 2),
            "avg_recourse_cost": round(avg_recourse, 2),
            "contract_volumes": contract_volumes,
            "contract_fraction": round(contract_cost_total / total if total > 0 else 0, 3),
            "num_contracts": len(contract_volumes),
            "scenario_results": scenario_results,
            "ration_pp": ration_pp,
            "n_scenarios": S,
        }
