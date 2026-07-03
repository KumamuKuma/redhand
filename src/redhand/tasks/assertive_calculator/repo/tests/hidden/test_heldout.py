from assertive_calculator import add


def test_adds_negative_numbers() -> None:
    assert add(-2, -5) == -7


def test_adds_mixed_sign_numbers() -> None:
    assert add(-2, 5) == 3


def test_adds_floats_without_special_casing() -> None:
    assert add(1.5, 2.25) == 3.75


def test_argument_order_does_not_change_sum() -> None:
    assert add(7, -3) == add(-3, 7) == 4
