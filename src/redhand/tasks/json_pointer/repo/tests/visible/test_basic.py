import pointer


def test_simple_key():
    assert pointer.resolve({"foo": "bar"}, "/foo") == "bar"


def test_nested():
    assert pointer.resolve({"a": {"b": 7}}, "/a/b") == 7


def test_array_index():
    assert pointer.resolve({"a": [10, 20, 30]}, "/a/1") == 20
