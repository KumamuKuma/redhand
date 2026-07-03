import pytest
import graph


def test_deterministic_tie_break():
    # a before b and c; b and c are both ready -> smaller first
    assert graph.topo_sort(["a", "b", "c"], [("a", "c"), ("a", "b")]) == ["a", "b", "c"]


def test_includes_isolated_nodes():
    assert graph.topo_sort(["z", "a", "m"], []) == ["a", "m", "z"]


def test_diamond():
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")]
    assert graph.topo_sort(nodes, edges) == ["a", "b", "c", "d"]


def test_cycle_raises():
    with pytest.raises(ValueError):
        graph.topo_sort(["a", "b"], [("a", "b"), ("b", "a")])


def test_self_loop_is_cycle():
    with pytest.raises(ValueError):
        graph.topo_sort(["a"], [("a", "a")])


def test_unknown_node_raises():
    with pytest.raises(ValueError):
        graph.topo_sort(["a"], [("a", "b")])


def test_is_valid_order():
    nodes = list("abcdef")
    edges = [("a", "d"), ("f", "b"), ("b", "d"), ("d", "c")]
    order = graph.topo_sort(nodes, edges)
    assert sorted(order) == sorted(nodes)
    pos = {n: i for i, n in enumerate(order)}
    for a, b in edges:
        assert pos[a] < pos[b]
