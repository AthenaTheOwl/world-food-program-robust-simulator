import json
import math
from contextlib import suppress
from pathlib import Path

from reports.scorecard import METRIC_FIELDS, generate_scorecard


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_scorecard_shape_and_determinism(scorecard_path):
    first_path = scorecard_path
    second_path = Path("reports/scorecard-second-test.jsonl")

    try:
        first_output = first_path.read_text(encoding="utf-8")
        generate_scorecard(second_path)
        second_output = second_path.read_text(encoding="utf-8")

        assert first_output == second_output

        rows = _read_jsonl(first_path)
        assert len(rows) == 11
        config_names = {row["config"] for row in rows}
        assert config_names == {
            "nominal",
            "robust@0.90",
            "robust@0.95",
            "robust@0.99",
            "adaptive@0.95",
            "adaptive@0.95/no-discount",
            "budget@1.10x",
            "fixed/no-discount",
            "fixed/discount",
            "recourse/no-discount",
            "recourse/discount",
        }

        required_columns = {
            "config",
            "robustness_level",
            "contract_discount",
            "total_cost",
            "cost_delta",
        }
        for row in rows:
            assert required_columns <= set(row)
            assert isinstance(row["cost_delta"], (int, float))
            assert not isinstance(row["cost_delta"], bool)
            assert math.isfinite(row["cost_delta"])
            for field_name in METRIC_FIELDS:
                value = row[field_name]
                if not row["config"].startswith(("nominal", "robust@", "budget@")) and field_name in {
                    "cost_per_person",
                    "nutrient_slack",
                }:
                    assert value is None
                else:
                    assert isinstance(value, (int, float))
                    assert not isinstance(value, bool)
                    assert math.isfinite(value)

        nominal = next(row for row in rows if row["config"] == "nominal")
        nominal_cost = nominal["total_cost"]
        for row in rows:
            if row["config"].startswith("robust@"):
                assert row["total_cost"] >= nominal_cost
        adaptive = next(row for row in rows if row["config"] == "adaptive@0.95")
        budget = next(row for row in rows if row["config"] == "budget@1.10x")
        assert adaptive["total_cost"] < nominal_cost
        assert budget["nutrient_slack"] > nominal["nutrient_slack"]
        for row in rows:
            assert row["unserved_demand"] == 0.0
    finally:
        with suppress(FileNotFoundError):
            second_path.unlink()
