import json
import math
from contextlib import suppress
from pathlib import Path

from reports.scorecard import METRIC_FIELDS, generate_scorecard


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_scorecard_shape_and_determinism():
    first_path = Path("reports/scorecard-first-test.jsonl")
    second_path = Path("reports/scorecard-second-test.jsonl")

    try:
        generate_scorecard(first_path)
        first_output = first_path.read_text(encoding="utf-8")
        generate_scorecard(second_path)
        second_output = second_path.read_text(encoding="utf-8")

        assert first_output == second_output

        rows = _read_jsonl(first_path)
        assert len(rows) == 6
        config_names = {row["config"] for row in rows}
        assert config_names == {
            "nominal",
            "robust@0.90",
            "robust@0.95",
            "robust@0.99",
            "adaptive@0.95",
            "budget@1.10x",
        }

        required_columns = {"config", "robustness_level", "total_cost", "cost_delta"}
        for row in rows:
            assert required_columns <= set(row)
            assert isinstance(row["cost_delta"], (int, float))
            assert not isinstance(row["cost_delta"], bool)
            assert math.isfinite(row["cost_delta"])
            for field_name in METRIC_FIELDS:
                value = row[field_name]
                if row["config"] == "adaptive@0.95" and field_name in {
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
    finally:
        with suppress(FileNotFoundError):
            first_path.unlink()
        with suppress(FileNotFoundError):
            second_path.unlink()
