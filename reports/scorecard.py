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
    except Exception as exc:
        raise ScorecardError(f"engine import failed: {exc}") from exc

    return Scenario, NominalLP, RobustSOCP, AdaptiveRobustModel, BudgetConstrainedModel, extract_solution


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
    }
    for field_name in METRIC_FIELDS:
        row[field_name] = _ensure_real_number(getattr(solution, field_name), field_name, config_name)
    return row


def _adaptive_metrics(scenario, adaptive_model, config_name: str, robustness_level: float) -> dict:
    model = adaptive_model(
        scenario,
        robustness_level=robustness_level,
        contract_discount=0.9,
        max_contract_fraction=0.8,
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
        "total_cost": _ensure_real_number(results["total_cost"], "total_cost", config_name),
        # Adaptive procurement is split between first-stage contracts and spot buys.
        "procurement_cost": round(contract_cost + spot_cost, 2),
        "transportation_cost": _ensure_real_number(
            results["transportation_cost"], "transportation_cost", config_name
        ),
        # AdaptiveRobustModel enforces hard nutrition bounds and exposes no slack/person metric.
        "cost_per_person": None,
        "nutrient_slack": None,
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
    print(
        f"Wrote {len(rows)} rows to {DEFAULT_OUTPUT_PATH}; "
        f"price_of_protection_0.95={price_of_protection:.2f}; "
        f"adaptive_saving={adaptive_saving:.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
