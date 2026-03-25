"""Monte Carlo simulation engine for empirical validation of robust solutions."""

import numpy as np
import pandas as pd

from core.scenario import Scenario
from models.solver_utils import SolutionResult


def generate_price_scenarios(
    scenario: Scenario, n_scenarios: int = 1000, seed: int = 42
) -> np.ndarray:
    """Generate random price realizations based on the scenario's uncertainty model.

    Returns:
        Array of shape (n_scenarios, len(procurement_index)) with realized prices.
    """
    rng = np.random.default_rng(seed)
    n_items = len(scenario.procurement_index)
    realized_prices = np.zeros((n_scenarios, n_items))

    # Build correlation group structure
    group_indices = {}  # group_name -> list of item indices
    for idx, (n, c) in enumerate(scenario.procurement_index):
        params = scenario.uncertainty_params.get((n, c), {})
        group = params.get("correlation_group")
        if isinstance(group, str) and group:
            if group not in group_indices:
                group_indices[group] = []
            group_indices[group].append(idx)

    # Generate independent noise for each item
    z_independent = rng.standard_normal((n_scenarios, n_items))

    for idx, (n, c) in enumerate(scenario.procurement_index):
        nominal_price = scenario.price_lookup[(n, c)]
        params = scenario.uncertainty_params.get((n, c), {})
        std_frac = params.get("price_std_fraction", 0.0)
        group = params.get("correlation_group")
        cross_corr = params.get("cross_correlation", 0.0)

        if np.isnan(std_frac) or std_frac == 0:
            realized_prices[:, idx] = nominal_price
            continue

        # Independent perturbation
        perturbation = std_frac * z_independent[:, idx]

        # Add the node-level shared perturbation from the homework formulation:
        # 0.30 * z_i + 0.05 * sum_k z_k for commodities sold at the same node.
        if isinstance(group, str) and group and not np.isnan(cross_corr) and cross_corr > 0:
            perturbation += cross_corr * z_independent[:, group_indices[group]].sum(axis=1)

        realized_prices[:, idx] = np.maximum(nominal_price * (1 + perturbation), 0.0)

    return realized_prices


def evaluate_solution(
    scenario: Scenario,
    solution: SolutionResult,
    realized_prices: np.ndarray,
    budget: float = None,
) -> pd.DataFrame:
    """Evaluate a fixed solution against realized price scenarios.

    Args:
        scenario: The scenario definition
        solution: A solved solution (procurement quantities are fixed)
        realized_prices: Array of shape (n_scenarios, n_items)
        budget: Optional budget threshold for feasibility checking

    Returns:
        DataFrame with columns: scenario_idx, realized_cost, nominal_cost,
        cost_increase_pct, feasible (if budget given)
    """
    n_scenarios = realized_prices.shape[0]
    procurement_index = scenario.procurement_index

    # Build procurement vector from solution
    proc_vector = np.array(
        [solution.procurement.get((n, c), 0.0) for (n, c) in procurement_index]
    )

    # Compute realized procurement costs for all scenarios at once
    # realized_prices: (n_scenarios, n_items), proc_vector: (n_items,)
    realized_proc_costs = realized_prices @ proc_vector

    # Transportation cost is fixed (doesn't depend on price uncertainty)
    transport_cost = solution.transportation_cost

    # Total realized costs
    realized_total = realized_proc_costs + transport_cost

    results = pd.DataFrame(
        {
            "scenario_idx": range(n_scenarios),
            "realized_procurement_cost": realized_proc_costs,
            "realized_total_cost": realized_total,
            "nominal_total_cost": solution.total_cost,
            "cost_increase_pct": (realized_total - solution.total_cost)
            / solution.total_cost
            * 100,
        }
    )

    if budget is not None:
        results["feasible"] = realized_total <= budget
        results["budget_excess"] = np.maximum(realized_total - budget, 0)

    return results


def compute_simulation_stats(results: pd.DataFrame) -> dict:
    """Compute summary statistics from simulation results."""
    stats = {
        "mean_cost": results["realized_total_cost"].mean(),
        "std_cost": results["realized_total_cost"].std(),
        "median_cost": results["realized_total_cost"].median(),
        "p5_cost": results["realized_total_cost"].quantile(0.05),
        "p95_cost": results["realized_total_cost"].quantile(0.95),
        "p99_cost": results["realized_total_cost"].quantile(0.99),
        "min_cost": results["realized_total_cost"].min(),
        "max_cost": results["realized_total_cost"].max(),
        "mean_increase_pct": results["cost_increase_pct"].mean(),
    }

    if "feasible" in results.columns:
        stats["feasibility_rate"] = results["feasible"].mean()
        stats["n_infeasible"] = (~results["feasible"]).sum()
        stats["mean_budget_excess"] = results["budget_excess"].mean()
        stats["max_budget_excess"] = results["budget_excess"].max()

    return stats
