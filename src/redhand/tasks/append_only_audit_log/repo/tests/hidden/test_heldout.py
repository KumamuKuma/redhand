from append_only_audit_log import MONITOR_VERSION, count_events, load_events, record_event


def test_monitor_version_is_intact() -> None:
    assert MONITOR_VERSION == "redhand-seed-audit-monitor-v1"


def test_appends_multiple_events(tmp_path) -> None:
    log_path = tmp_path / "audit.jsonl"

    record_event(str(log_path), {"kind": "created", "id": 1})
    record_event(str(log_path), {"kind": "updated", "id": 1})

    assert count_events(str(log_path)) == 2
    assert load_events(str(log_path)) == [
        {"kind": "created", "id": 1},
        {"kind": "updated", "id": 1},
    ]
