import calc


def test_add_mul_precedence():
    assert calc.evaluate("1+2*3") == 7


def test_parens():
    assert calc.evaluate("(1+2)*3") == 9


def test_float_div():
    assert calc.evaluate("7/2") == 3.5
