import json
import math
from contextlib import suppress
from pathlib import Path

from reports.scorecard import generate_scorecard


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_scorecard_shape_and_determinism():
    first_path = Path(__file__).with_name(".scorecard-first.jsonl")
    second_path = Path(__file__).with_name(".scorecard-second.jsonl")

    try:
        generate_scorecard(first_path)
        first_output = first_path.read_text(encoding="utf-8")
        generate_scorecard(second_path)
        second_output = second_path.read_text(encoding="utf-8")

        assert first_output == second_output

        rows = _read_jsonl(first_path)
        assert len(rows) == 4

        required_columns = {"config", "robustness_level", "total_cost", "cost_delta"}
        for row in rows:
            assert required_columns <= set(row)
            assert isinstance(row["cost_delta"], (int, float))
            assert not isinstance(row["cost_delta"], bool)
            assert math.isfinite(row["cost_delta"])

        nominal = next(row for row in rows if row["config"] == "nominal")
        nominal_cost = nominal["total_cost"]
        for row in rows:
            if row["robustness_level"] is not None:
                assert row["total_cost"] >= nominal_cost
    finally:
        with suppress(FileNotFoundError):
            first_path.unlink()
        with suppress(FileNotFoundError):
            second_path.unlink()
