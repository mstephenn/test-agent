from pathlib import Path
from test_agent.coverage import parse_coverage, CoverageData
import pytest

FIXTURES = Path("tests/fixtures")


def test_parse_lcov():
    data = parse_coverage(FIXTURES / "sample_lcov.info")
    assert "src/payments/charge.py" in data.uncovered_lines
    assert 1 in data.uncovered_lines["src/payments/charge.py"]
    assert 2 in data.uncovered_lines["src/payments/charge.py"]


def test_parse_json():
    data = parse_coverage(FIXTURES / "sample_coverage.json")
    assert "src/payments/charge.py" in data.uncovered_lines


def test_parse_cobertura():
    data = parse_coverage(FIXTURES / "sample_cobertura.xml")
    assert "src/payments/charge.py" in data.uncovered_lines


def test_parse_unknown_format_raises(tmp_path):
    f = tmp_path / "coverage.unknown"
    f.write_text("data")
    with pytest.raises(ValueError, match="Unsupported coverage format"):
        parse_coverage(f)
