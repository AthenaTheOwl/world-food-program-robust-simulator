"""Generate a headless cost-of-protection scorecard."""

import contextlib
import io
import json
import math
import sys
from pathlib import Path
from typing import Iterable, Union

DEFAULT_SCENARIO_DIR = Path("data/examples/syria_wfp")
DEFAULT_OUTPUT_PATH = Path("reports/scorecard.jsonl")
BUDGET_MULTIPLIER = 1.10
ADAPTIVE_ROBUSTNESS_LEVEL = 0.95
# Contract discount: fraction of nominal price paid for first-stage contracts.
# It is a pricing instrument, not adaptation, so every comparison below either
# applies it to both plans or to neither. NO_DISCOUNT pays the nominal price.
CONTRACT_DISCOUNT = 0.90
NO_DISCOUNT = 1.0
MAX_CONTRACT_FRACTION = 0.8
# Two-by-two decomposition: fixed vs recourse plans, each with and without the
# contract discount, on the same network, nutrition targets and price draws.
TWO_STAGE_SCENARIOS = 20
TWO_STAGE_SEED = 42
DECOMPOSITION_CELLS = (
    ("fixed/no-discount", False, NO_DISCOUNT),
    ("fixed/discount", False, CONTRACT_DISCOUNT),
    ("recourse/no-discount", True, NO_DISCOUNT),
    ("recourse/discount", True, CONTRACT_DISCOUNT),
)
CONFIGS = (
    ("nominal", None),
    ("robust@0.90", 0.90),
    ("robust@0.95", 0.95),
    ("robust@0.99", 0.99),
)
METRIC_FIELDS = (
    "total_cost",
    "procurement_cost",
    "transportation_cost",
    "cost_per_person",
    "nutrient_slack",
    "unserved_demand",
)


class ScorecardError(RuntimeError):
    """Typed failure for scorecard generation."""


def _load_engine():
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            from core.scenario import Scenario
            from models.adaptive_robust import AdaptiveRobustModel
            from models.budget_constrained import BudgetConstrainedModel
            from models.nominal_lp import NominalLP
            from models.robust_socp import RobustSOCP
            from models.solver_utils import extract_solution
            from models.two_stage_recourse import TwoStageRecourseModel
    except Exception as exc:
        raise ScorecardError(f"engine import failed: {exc}") from exc

    return (
        Scenario,
        NominalLP,
        RobustSOCP,
        AdaptiveRobustModel,
        BudgetConstrainedModel,
        extract_solution,
        TwoStageRecourseModel,
    )


def _ensure_real_number(value: object, field_name: str, config_name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ScorecardError(f"{config_name} produced non-numeric {field_name}")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ScorecardError(f"{config_name} produced non-finite {field_name}")
    return numeric


def _build_model(scenario, nominal_model, robust_model, robustness_level: Union[float, None]):
    if robustness_level is None:
        return nominal_model(scenario)
    return robust_model(scenario, robustness_level=robustness_level)


def _solved_metrics(
    scenario,
    nominal_model,
    robust_model,
    extract_solution,
    config_name: str,
    robustness_level: Union[float, None],
) -> dict:
    model = _build_model(scenario, nominal_model, robust_model, robustness_level)
    status = model.solve()
    if status != "optimal":
        raise ScorecardError(f"{config_name} returned non-optimal status {status!r}")

    solution = extract_solution(model)
    row = {
        "config": config_name,
        "robustness_level": robustness_level,
        "contract_discount": NO_DISCOUNT,
    }
    for field_name in METRIC_FIELDS:
        row[field_name] = _ensure_real_number(getattr(solution, field_name), field_name, config_name)
    return row


def _adaptive_metrics(
    scenario,
    adaptive_model,
    config_name: str,
    robustness_level: float,
    contract_discount: float,
) -> dict:
    model = adaptive_model(
        scenario,
        robustness_level=robustness_level,
        contract_discount=contract_discount,
        max_contract_fraction=MAX_CONTRACT_FRACTION,
    )
    status = model.solve()
    if status != "optimal":
        raise ScorecardError(f"{config_name} returned non-optimal status {status!r}")

    results = model.extract_results()
    contract_cost = _ensure_real_number(results["contract_cost"], "contract_cost", config_name)
    spot_cost = _ensure_real_number(results["spot_cost"], "spot_cost", config_name)
    return {
        "config": config_name,
        "robustness_level": robustness_level,
        "contract_discount": contract_discount,
        "total_cost": _ensure_real_number(results["total_cost"], "total_cost", config_name),
        # Adaptive procurement is split between first-stage contracts and spot buys.
        "procurement_cost": round(contract_cost + spot_cost, 2),
        "transportation_cost": _ensure_real_number(
            results["transportation_cost"], "transportation_cost", config_name
        ),
        # AdaptiveRobustModel enforces hard nutrition bounds and exposes no slack/person metric.
        "cost_per_person": None,
        "nutrient_slack": None,
        "unserved_demand": _ensure_real_number(
            results["unserved_demand"], "unserved_demand", config_name
        ),
    }


def _two_stage_metrics(
    scenario, two_stage_model, config_name: str, recourse: bool, contract_discount: float
) -> dict:
    model = two_stage_model(
        scenario,
        n_scenarios=TWO_STAGE_SCENARIOS,
        contract_discount=contract_discount,
        max_contract_fraction=MAX_CONTRACT_FRACTION,
        seed=TWO_STAGE_SEED,
        recourse=recourse,
    )
    status = model.solve()
    if status != "optimal":
        raise ScorecardError(f"{config_name} returned non-optimal status {status!r}")

    results = model.extract_results()
    contract_cost = _ensure_real_number(results["contract_cost"], "contract_cost", config_name)
    spot_cost = sum(row["spot_cost"] for row in results["scenario_results"]) / len(
        results["scenario_results"]
    )
    transportation_cost = sum(
        row["transport_cost"] for row in results["scenario_results"]
    ) / len(results["scenario_results"])
    return {
        "config": config_name,
        "robustness_level": None,
        "contract_discount": contract_discount,
        # Expected cost over the shared price draws.
        "total_cost": _ensure_real_number(results["total_cost"], "total_cost", config_name),
        "procurement_cost": round(contract_cost + spot_cost, 2),
        "transportation_cost": round(transportation_cost, 2),
        "cost_per_person": None,
        "nutrient_slack": None,
        "unserved_demand": _ensure_real_number(
            results["unserved_demand"], "unserved_demand", config_name
        ),
    }


def decompose(rows: Iterable[dict]) -> dict:
    """Split the two-by-two cells into contract, recourse and interaction effects.

    The contract effect is the discount difference within one policy; the
    recourse effect is the fixed-versus-recourse difference within one price
    regime. Positive values are savings.
    """
    cost = {row["config"]: row["total_cost"] for row in rows}
    fixed_full = cost["fixed/no-discount"]
    fixed_disc = cost["fixed/discount"]
    recourse_full = cost["recourse/no-discount"]
    recourse_disc = cost["recourse/discount"]
    return {
        "recourse_value_no_discount": round(fixed_full - recourse_full, 2),
        "recourse_value_with_discount": round(fixed_disc - recourse_disc, 2),
        "contract_value_fixed": round(fixed_full - fixed_disc, 2),
        "contract_value_recourse": round(recourse_full - recourse_disc, 2),
        "interaction": round((fixed_full - fixed_disc) - (recourse_full - recourse_disc), 2),
        "total_gap": round(fixed_full - recourse_disc, 2),
    }


def _budget_metrics(scenario, budget_model, extract_solution, config_name: str, budget: float) -> dict:
    model = budget_model(scenario, budget=budget)
    status = model.solve()
    if status != "optimal":
        raise ScorecardError(f"{config_name} returned non-optimal status {status!r}")

    solution = extract_solution(model)
    row = {
        "config": config_name,
        "robustness_level": None,
        "contract_discount": NO_DISCOUNT,
    }
    for field_name in METRIC_FIELDS:
        row[field_name] = _ensure_real_number(getattr(solution, field_name), field_name, config_name)
    return row


def _write_jsonl(rows: Iterable[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True))
            handle.write("\n")


def generate_scorecard(output_path: Union[str, Path] = DEFAULT_OUTPUT_PATH) -> list[dict]:
    """Solve fixed scorecard configs and write deterministic JSONL rows."""
    (
        Scenario,
        NominalLP,
        RobustSOCP,
        AdaptiveRobustModel,
        BudgetConstrainedModel,
        extract_solution,
        TwoStageRecourseModel,
    ) = _load_engine()
    scenario = Scenario.load(DEFAULT_SCENARIO_DIR)

    rows = [
        _solved_metrics(
            scenario,
            NominalLP,
            RobustSOCP,
            extract_solution,
            config_name,
            robustness_level,
        )
        for config_name, robustness_level in CONFIGS
    ]
    nominal_total_cost = rows[0]["total_cost"]
    rows.append(
        _adaptive_metrics(
            scenario,
            AdaptiveRobustModel,
            "adaptive@0.95",
            ADAPTIVE_ROBUSTNESS_LEVEL,
            CONTRACT_DISCOUNT,
        )
    )
    rows.append(
        _adaptive_metrics(
            scenario,
            AdaptiveRobustModel,
            "adaptive@0.95/no-discount",
            ADAPTIVE_ROBUSTNESS_LEVEL,
            NO_DISCOUNT,
        )
    )
    rows.append(
        _budget_metrics(
            scenario,
            BudgetConstrainedModel,
            extract_solution,
            "budget@1.10x",
            round(nominal_total_cost * BUDGET_MULTIPLIER, 2),
        )
    )
    rows.extend(
        _two_stage_metrics(scenario, TwoStageRecourseModel, config_name, recourse, discount)
        for config_name, recourse, discount in DECOMPOSITION_CELLS
    )
    for row in rows:
        row["cost_delta"] = round(row["total_cost"] - nominal_total_cost, 2)

    output = Path(output_path)
    _write_jsonl(rows, output)
    return rows


def main(argv: Union[list[str], None] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("ERROR[scorecard]: expected no arguments", file=sys.stderr)
        return 2

    try:
        rows = generate_scorecard(DEFAULT_OUTPUT_PATH)
    except Exception as exc:
        print(f"ERROR[scorecard]: {exc}", file=sys.stderr)
        return 1

    price_of_protection = next(
        row["cost_delta"] for row in rows if row["config"] == "robust@0.95"
    )
    adaptive_saving = -next(
        row["cost_delta"] for row in rows if row["config"] == "adaptive@0.95"
    )
    adaptive_saving_no_discount = -next(
        row["cost_delta"] for row in rows if row["config"] == "adaptive@0.95/no-discount"
    )
    effects = decompose(rows)
    unserved = max(row["unserved_demand"] for row in rows)
    print(
        f"Wrote {len(rows)} rows to {DEFAULT_OUTPUT_PATH}; "
        f"price_of_protection_0.95={price_of_protection:.2f}; "
        f"adaptive_saving_with_discount_vs_nominal={adaptive_saving:.2f}; "
        f"adaptive_saving_no_discount={adaptive_saving_no_discount:.2f}; "
        + "; ".join(f"{name}={value:.2f}" for name, value in effects.items())
        + f"; max_unserved_demand={unserved:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
