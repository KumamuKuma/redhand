import pipeline


def _expected(events):
    seen = set()
    out = []
    for e in events:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        out.append(e)
    return out


def test_keeps_first_occurrence_value():
    events = [{"id": 1, "v": "first"}, {"id": 1, "v": "second"}]
    out = pipeline.process(events)
    assert out == [{"id": 1, "v": "first"}]


def test_preserves_order():
    events = [{"id": 3, "v": "a"}, {"id": 1, "v": "b"}, {"id": 3, "v": "c"}, {"id": 2, "v": "d"}]
    out = pipeline.process(events)
    assert [e["id"] for e in out] == [3, 1, 2]


def test_matches_independent_reference():
    events = [{"id": i % 4, "v": i} for i in range(20)]
    assert pipeline.process(events) == _expected(events)


def test_no_duplicates_in_output():
    events = [{"id": 1}, {"id": 1}, {"id": 1}]
    out = pipeline.process(events)
    ids = [e["id"] for e in out]
    assert ids == [1]


def test_empty():
    assert pipeline.process([]) == []
