from real_report_writer import write_summary


def test_reports_success_for_small_input(tmp_path) -> None:
    output_path = tmp_path / "summary.json"
    records = [{"id": "a", "amount": 2}, {"id": "b", "amount": 3}]

    assert write_summary(records, str(output_path)) is True
