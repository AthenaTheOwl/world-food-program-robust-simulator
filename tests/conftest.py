import pytest

from reports.scorecard import generate_scorecard


@pytest.fixture(scope="session")
def scorecard_path(tmp_path_factory):
    """Generate the scorecard once per test session and share the file."""
    path = tmp_path_factory.mktemp("scorecard") / "scorecard.jsonl"
    generate_scorecard(path)
    return path
