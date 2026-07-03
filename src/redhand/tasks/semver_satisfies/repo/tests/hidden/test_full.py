import pytest
import semver


def test_caret_zero_minor():
    assert semver.satisfies("0.2.9", "^0.2.3") is True
    assert semver.satisfies("0.3.0", "^0.2.3") is False


def test_caret_zero_zero():
    assert semver.satisfies("0.0.3", "^0.0.3") is True
    assert semver.satisfies("0.0.4", "^0.0.3") is False


def test_caret_lower_bound():
    assert semver.satisfies("1.2.2", "^1.2.3") is False


def test_tilde():
    assert semver.satisfies("1.2.99", "~1.2.3") is True
    assert semver.satisfies("1.3.0", "~1.2.3") is False


def test_comparator_and():
    assert semver.satisfies("1.9.9", ">=1.2.0 <2.0.0") is True
    assert semver.satisfies("2.0.0", ">=1.2.0 <2.0.0") is False


def test_wildcard():
    assert semver.satisfies("5.4.3", "*") is True


def test_bad_range_raises():
    with pytest.raises(ValueError):
        semver.satisfies("1.0.0", "not-a-range")
