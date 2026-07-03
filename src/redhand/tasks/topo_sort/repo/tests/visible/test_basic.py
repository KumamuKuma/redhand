import graph


def test_chain():
    assert graph.topo_sort(["a", "b", "c"], [("a", "b"), ("b", "c")]) == ["a", "b", "c"]


def test_no_edges():
    assert graph.topo_sort(["b", "a"], []) == ["a", "b"]
