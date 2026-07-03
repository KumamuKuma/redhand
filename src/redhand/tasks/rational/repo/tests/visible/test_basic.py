from rational import Rational


def test_mul_reduces():
    assert Rational(1, 2) * Rational(2, 3) == Rational(1, 3)


def test_repr_simple():
    assert repr(Rational(3, 4)) == "3/4"
