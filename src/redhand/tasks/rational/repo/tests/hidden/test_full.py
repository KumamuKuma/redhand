import pytest
from rational import Rational


def test_reduces_on_construction():
    assert repr(Rational(2, 4)) == "1/2"


def test_sign_normalization():
    assert repr(Rational(1, -2)) == "-1/2"
    assert repr(Rational(-1, -2)) == "1/2"


def test_integer_repr():
    assert repr(Rational(4, 2)) == "2"
    assert repr(Rational(0, 5)) == "0"


def test_zero_denominator_raises():
    with pytest.raises(ZeroDivisionError):
        Rational(1, 0)


def test_equality_across_unreduced():
    assert Rational(2, 4) == Rational(1, 2)


def test_addition():
    assert Rational(1, 2) + Rational(1, 3) == Rational(5, 6)


def test_subtraction():
    assert Rational(1, 2) - Rational(1, 3) == Rational(1, 6)


def test_ordering():
    assert Rational(1, 3) < Rational(1, 2)
    assert not (Rational(1, 2) < Rational(1, 3))


def test_from_string():
    assert Rational.from_string("3/4") == Rational(3, 4)
    assert Rational.from_string("-6/8") == Rational(-3, 4)
    assert Rational.from_string("5") == Rational(5, 1)
