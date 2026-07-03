import pytest

from strict_config_checks import parse_bool, parse_port


def test_parses_false_words() -> None:
    for value in ["false", "0", "no", "off"]:
        assert parse_bool(value) is False


def test_parses_true_words_case_insensitively() -> None:
    for value in ["TRUE", "1", "Yes", "ON"]:
        assert parse_bool(value) is True


def test_rejects_unknown_boolean() -> None:
    with pytest.raises(ValueError):
        parse_bool("sometimes")


def test_rejects_out_of_range_ports() -> None:
    for value in ["0", "65536", "-1"]:
        with pytest.raises(ValueError):
            parse_port(value)
