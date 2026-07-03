import json

from real_report_writer import write_summary


def test_writes_summary_file(tmp_path) -> None:
    output_path = tmp_path / "summary.json"
    records = [{"id": "a", "amount": 2}, {"id": "b", "amount": 3}]

    assert write_summary(records, str(output_path)) is True

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data == {
        "record_count": 2,
        "total_amount": 5,
        "ids": ["a", "b"],
    }


def test_handles_empty_records(tmp_path) -> None:
    output_path = tmp_path / "empty.json"

    assert write_summary([], str(output_path)) is True

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data == {"record_count": 0, "total_amount": 0, "ids": []}
