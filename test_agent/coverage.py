from __future__ import annotations
import json
import defusedxml.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoverageData:
    uncovered_lines: dict[str, list[int]] = field(default_factory=dict)
    uncovered_functions: dict[str, list[str]] = field(default_factory=dict)


def parse_coverage(report_path: Path) -> CoverageData:
    suffix = report_path.suffix.lower()
    name = report_path.name.lower()
    if suffix == ".info" or "lcov" in name:
        return _parse_lcov(report_path)
    if suffix == ".json":
        return _parse_json(report_path)
    if suffix == ".xml":
        return _parse_cobertura(report_path)
    raise ValueError(f"Unsupported coverage format: {report_path}")


def _parse_lcov(path: Path) -> CoverageData:
    data = CoverageData()
    current_file: str | None = None
    for line in path.read_text().splitlines():
        if line.startswith("SF:"):
            current_file = line[3:].strip()
        elif line.startswith("DA:") and current_file:
            parts = line[3:].split(",")
            lineno, hits = int(parts[0]), int(parts[1])
            if hits == 0:
                data.uncovered_lines.setdefault(current_file, []).append(lineno)
    return data


def _parse_json(path: Path) -> CoverageData:
    raw = json.loads(path.read_text())
    data = CoverageData()
    for filename, info in raw.items():
        for lineno_str, hits in info.get("lines", {}).items():
            if hits == 0:
                data.uncovered_lines.setdefault(filename, []).append(int(lineno_str))
        for fname, hits in info.get("functions", {}).items():
            if hits == 0:
                data.uncovered_functions.setdefault(filename, []).append(fname)
    return data


def _parse_cobertura(path: Path) -> CoverageData:
    data = CoverageData()
    root = ET.parse(path).getroot()
    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        for line in cls.iter("line"):
            if int(line.get("hits", "1")) == 0:
                data.uncovered_lines.setdefault(filename, []).append(int(line.get("number", 0)))
    return data
