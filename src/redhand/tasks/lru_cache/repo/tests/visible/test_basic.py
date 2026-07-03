from cache import LRUCache


def test_put_get():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1
    assert c.get("b") == 2


def test_miss():
    c = LRUCache(2)
    assert c.get("nope") == -1
