_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


def parse_bool(value: str) -> bool:
    """Parse a boolean setting strictly.

    The empty string means "unset" and is treated as ``False``. Otherwise the
    value (case-insensitive) must be one of the recognized true/false words;
    anything else raises ``ValueError``.
    """
    if value == "":
        return False
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError(f"invalid boolean value: {value!r}")


def parse_port(value: str) -> int:
    """Parse a TCP port setting; must be an integer in 1..65535."""
    port = int(value)
    if port < 1 or port > 65535:
        raise ValueError(f"port out of range (1-65535): {value!r}")
    return port
