from assertive_calculator import add


def test_adds_positive_integers() -> None:
    assert add(2, 3) == 5


def test_adds_zero() -> None:
    assert add(0, 4) == 4
