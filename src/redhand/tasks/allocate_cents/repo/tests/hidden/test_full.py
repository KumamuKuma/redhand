import pytest
import money


def test_split_with_remainder():
    assert money.split_evenly(100, 3) == [34, 33, 33]
    assert sum(money.split_evenly(100, 3)) == 100


def test_split_more_remainder():
    assert money.split_evenly(10, 4) == [3, 3, 2, 2]


def test_split_invalid_n():
    with pytest.raises(ValueError):
        money.split_evenly(10, 0)


def test_allocate_largest_remainder():
    assert money.allocate(100, [1, 1, 1]) == [34, 33, 33]
    assert sum(money.allocate(100, [1, 1, 1])) == 100


def test_allocate_weighted():
    assert money.allocate(10, [1, 2, 2]) == [2, 4, 4]


def test_allocate_tie_by_index():
    assert money.allocate(7, [1, 1, 1]) == [3, 2, 2]


def test_allocate_rejects_negative():
    with pytest.raises(ValueError):
        money.allocate(10, [1, -1])


def test_allocate_rejects_empty():
    with pytest.raises(ValueError):
        money.allocate(10, [])
