import pytest
from cache import LRUCache


def test_evicts_least_recently_used():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("c", 3)          # evicts "a"
    assert c.get("a") == -1
    assert c.get("b") == 2
    assert c.get("c") == 3


def test_get_refreshes_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1  # "a" now most recent
    c.put("c", 3)           # evicts "b", not "a"
    assert c.get("a") == 1
    assert c.get("b") == -1


def test_update_refreshes_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 10)          # update refreshes "a"
    c.put("c", 3)           # evicts "b"
    assert c.get("a") == 10
    assert c.get("b") == -1


def test_capacity_must_be_positive():
    with pytest.raises(ValueError):
        LRUCache(0)
