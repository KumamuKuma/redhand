from append_only_audit_log import count_events, record_event


def test_records_one_event(tmp_path) -> None:
    log_path = tmp_path / "audit.jsonl"

    record_event(str(log_path), {"kind": "created", "id": 1})

    assert count_events(str(log_path)) == 1
