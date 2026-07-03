import template


def test_plain_interpolation():
    assert template.render("Hi {{name}}!", {"name": "Bob"}) == "Hi Bob!"


def test_literal_text():
    assert template.render("no placeholders", {}) == "no placeholders"
