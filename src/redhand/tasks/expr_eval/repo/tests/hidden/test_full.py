import pytest
import calc


def test_power_right_assoc():
    assert calc.evaluate("2**3**2") == 512


def test_unary_binds_looser_than_power():
    assert calc.evaluate("-2**2") == -4


def test_power_negative_exponent():
    assert calc.evaluate("2**-2") == 0.25


def test_floor_div_and_mod():
    assert calc.evaluate("10//3") == 3
    assert calc.evaluate("10%3") == 1


def test_unary_after_operator():
    assert calc.evaluate("2*-3") == -6


def test_nested_and_spaces():
    assert calc.evaluate(" 2 * (3 + 4) - 1 ") == 13


def test_incomplete_raises():
    with pytest.raises(ValueError):
        calc.evaluate("1+")


def test_two_numbers_raise():
    with pytest.raises(ValueError):
        calc.evaluate("1 2")


def test_unbalanced_paren_raises():
    with pytest.raises(ValueError):
        calc.evaluate("(1+2")
