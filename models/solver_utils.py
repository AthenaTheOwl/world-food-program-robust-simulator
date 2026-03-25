"""Solution extraction and performance metrics."""

from dataclasses import dataclass, field
import numpy as np

from config import ACTIVE_THRESHOLD


@dataclass
class SolutionResult:
    """Structured representation of an optimization solution."""

    status: str
    total_cost: float = 0.0
    procurement_cost: float = 0.0
    transportation_cost: float = 0.0
    nutrient_slack: float = 0.0
    robustness_level: float = 0.5

    # Breakdown dicts
    procurement: dict = field(default_factory=dict)  # {(node, commodity): tons}
    flows: dict = field(default_factory=dict)  # {(source, target, commodity): tons}
    delivery: dict = field(default_factory=dict)  # {(demand_node, commodity): tons}
    transportation: dict = field(default_factory=dict)  # {(source, target): total_tons}
    ration_pp: dict = field(default_factory=dict)  # {commodity: kg/person/day}
    nutrients_pp: dict = field(default_factory=dict)  # {nutrient: amount/person}

    # Performance metrics
    cost_per_person: float = 0.0
    procurement_ratio: float = 0.0  # procurement_cost / total_cost
    transportation_ratio: float = 0.0  # transportation_cost / total_cost
    international_procurement_ratio: float = 0.0  # intl_proc_cost / procurement_cost
    num_active_procurement: int = 0
    num_active_transport: int = 0

    @property
    def is_optimal(self):
        return self.status in ("optimal", "optimal_inaccurate")


def extract_solution(model, robustness_level: float = 0.5) -> SolutionResult:
    """Extract a structured SolutionResult from a solved BaseModel."""
    if not model.is_solved:
        return SolutionResult(status=model.problem.status if model.problem else "unsolved")

    s = model.scenario
    v = model.variables

    total_cost = float(v["procurement_cost"].value + v["transportation_cost"].value)
    proc_cost = float(v["procurement_cost"].value)
    trans_cost = float(v["transportation_cost"].value)
    slack = float(v["nutrient_slack"].value)

    # Extract procurement values
    procurement = {}
    for (n, c) in s.procurement_index:
        val = float(v["procurement"][(n, c)].value)
        if val > ACTIVE_THRESHOLD:
            procurement[(n, c)] = val

    # Extract flows
    flows = {}
    for (a, b) in s.edge_index:
        for c in s.commodity_list:
            val = float(v["flow"][(a, b, c)].value)
            if val > ACTIVE_THRESHOLD:
                flows[(a, b, c)] = val

    # Extract delivery
    delivery = {}
    for d in s.demand_nodes:
        for c in s.commodity_list:
            val = float(v["delivery"][(d, c)].value)
            if val > ACTIVE_THRESHOLD:
                delivery[(d, c)] = val

    # Extract transportation totals
    transportation = {}
    for (a, b) in s.edge_index:
        val = float(v["transportation"][(a, b)].value)
        if val > ACTIVE_THRESHOLD:
            transportation[(a, b)] = val

    # Extract ration per person
    ration_pp = {}
    for c in s.commodity_list:
        val = float(v["ration_pp"][c].value)
        if val > ACTIVE_THRESHOLD:
            ration_pp[c] = val

    # Extract nutrients per person
    nutrients_pp = {n: float(v["nutrients_pp"][n].value) for n in s.nutrient_list}

    # Compute performance metrics
    intl_types = {"supplier_international"}
    intl_proc_cost = sum(
        s.price_lookup[(n, c)] * procurement.get((n, c), 0)
        for (n, c) in s.procurement_index
        if s.get_node_type(n) in intl_types
    )

    effective_people = slack * s.total_demand if slack > 0 else 0
    cost_per_person = total_cost / effective_people if effective_people > 0 else float("inf")

    num_active_proc = len(procurement)
    num_active_trans = len(transportation)

    return SolutionResult(
        status=model.problem.status,
        total_cost=round(total_cost, 2),
        procurement_cost=round(proc_cost, 2),
        transportation_cost=round(trans_cost, 2),
        nutrient_slack=round(slack, 4),
        robustness_level=robustness_level,
        procurement=procurement,
        flows=flows,
        delivery=delivery,
        transportation=transportation,
        ration_pp=ration_pp,
        nutrients_pp=nutrients_pp,
        cost_per_person=round(cost_per_person, 4),
        procurement_ratio=round(proc_cost / total_cost, 3) if total_cost > 0 else 0,
        transportation_ratio=round(trans_cost / total_cost, 3) if total_cost > 0 else 0,
        international_procurement_ratio=round(intl_proc_cost / proc_cost, 3) if proc_cost > 0 else 0,
        num_active_procurement=num_active_proc,
        num_active_transport=num_active_trans,
    )


def solution_to_metrics_dict(sol: SolutionResult) -> dict:
    """Convert solution to a flat dict for display in tables/DataFrames."""
    return {
        "Robustness (p)": f"{sol.robustness_level:.1%}",
        "Total Cost ($)": f"{sol.total_cost:,.0f}",
        "Procurement/Total": f"{sol.procurement_ratio:.1%}",
        "Transport/Total": f"{sol.transportation_ratio:.1%}",
        "Intl/Procurement": f"{sol.international_procurement_ratio:.1%}",
        "Nutrient Slack": f"{sol.nutrient_slack:.3f}",
        "Cost/Person ($)": f"{sol.cost_per_person:,.2f}",
        "Active Procurements": sol.num_active_procurement,
        "Active Routes": sol.num_active_transport,
    }
