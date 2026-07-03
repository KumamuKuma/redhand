import json
import os
import tempfile
import pipeline

HERE = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA = os.path.join(HERE, "data.csv")


def test_report_has_total_and_count():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "report.json")
        report = pipeline.build_report(DATA, out)
        assert report["count"] == 6
        assert "total" in report
        with open(out) as fh:
            on_disk = json.load(fh)
        assert on_disk["count"] == 6
