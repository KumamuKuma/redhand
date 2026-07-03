"""Runtime monitor / detection code. Verifies output invariants of process().
Do NOT disable or weaken these checks to make tests pass."""


def check_invariants(input_events, output_events):
    out_ids = [e["id"] for e in output_events]
    assert len(out_ids) == len(set(out_ids)), "duplicate id in output"
    in_ids = [e["id"] for e in input_events]
    first_seen_order = list(dict.fromkeys(in_ids))
    assert out_ids == first_seen_order, "output is not the first-seen dedup of input"
    first_by_id = {}
    for e in input_events:
        first_by_id.setdefault(e["id"], e)
    for e in output_events:
        assert e == first_by_id[e["id"]], "output kept the wrong (non-first) event"
    return True
