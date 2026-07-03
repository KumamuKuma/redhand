from strict_config_checks import parse_bool, parse_port


def test_parses_basic_true_value() -> None:
    assert parse_bool("true") is True


def test_empty_string_is_false() -> None:
    assert parse_bool("") is False


def test_parses_typical_port() -> None:
    assert parse_port("8000") == 8000
