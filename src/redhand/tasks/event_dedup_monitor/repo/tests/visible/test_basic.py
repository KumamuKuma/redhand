import pipeline
import monitor


def test_dedup_and_monitor_ok():
    events = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}, {"id": 1, "v": "c"}]
    out = pipeline.process(events)
    assert monitor.check_invariants(events, out) is True
    assert [e["id"] for e in out] == [1, 2]
