import pytest
import template


def test_escapes_html():
    out = template.render("<b>{{x}}</b>", {"x": "<script>"})
    assert out == "<b>&lt;script&gt;</b>"


def test_escapes_quotes_and_amp():
    out = template.render("{{x}}", {"x": 'a & "b" & \'c\''})
    assert out == "a &amp; &quot;b&quot; &amp; &#x27;c&#x27;"


def test_triple_brace_is_raw():
    assert template.render("{{{x}}}", {"x": "<b>"}) == "<b>"


def test_literal_amp_not_escaped():
    # ampersand that is not part of a value must be left as-is
    assert template.render("a & b {{x}}", {"x": "z"}) == "a & b z"


def test_missing_key_raises():
    with pytest.raises(KeyError):
        template.render("{{missing}}", {})
