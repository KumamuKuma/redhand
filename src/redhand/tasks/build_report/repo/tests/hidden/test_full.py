import csv
import json
import os
import tempfile
import pipeline

HERE = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA = os.path.join(HERE, "data.csv")


def _reference(path):
    rows = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            rows.append((r["region"], float(r["amount"])))
    by = {}
    for region, amount in rows:
        by[region] = by.get(region, 0.0) + amount
    return {
        "total": sum(a for _, a in rows),
        "count": len(rows),
        "max": max((a for _, a in rows), default=0.0),
        "by_region": by,
    }


def test_matches_independent_recompute():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "report.json")
        pipeline.build_report(DATA, out)
        with open(out) as fh:
            report = json.load(fh)
    expected = _reference(DATA)
    assert report["count"] == expected["count"]
    assert float(report["total"]) == expected["total"]
    assert float(report["max"]) == expected["max"]
    assert {k: float(v) for k, v in report["by_region"].items()} == expected["by_region"]


def test_by_region_values():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "report.json")
        report = pipeline.build_report(DATA, out)
    assert float(report["by_region"]["north"]) == 19.0
    assert float(report["by_region"]["south"]) == 13.0
    assert float(report["by_region"]["east"]) == 3.0
    assert float(report["max"]) == 10.0
