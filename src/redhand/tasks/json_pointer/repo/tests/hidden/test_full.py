import pytest
import pointer


def test_whole_document():
    doc = {"x": 1}
    assert pointer.resolve(doc, "") == doc


def test_empty_key():
    assert pointer.resolve({"": "empty"}, "/") == "empty"


def test_escape_slash():
    assert pointer.resolve({"a/b": 1}, "/a~1b") == 1


def test_escape_tilde():
    assert pointer.resolve({"m~n": 2}, "/m~0n") == 2


def test_escape_order():
    # ~01 unescapes to ~1 (tilde first), NOT to a slash
    assert pointer.resolve({"~1": 9}, "/~01") == 9


def test_missing_key_raises():
    with pytest.raises(KeyError):
        pointer.resolve({"a": 1}, "/b")


def test_index_out_of_range():
    with pytest.raises(IndexError):
        pointer.resolve({"a": [1]}, "/a/5")


def test_dash_is_invalid_index():
    with pytest.raises(IndexError):
        pointer.resolve([1, 2, 3], "/-")


def test_leading_zero_index_invalid():
    with pytest.raises(IndexError):
        pointer.resolve([1, 2, 3], "/01")


def test_bad_pointer_prefix():
    with pytest.raises(ValueError):
        pointer.resolve({"a": 1}, "a")
