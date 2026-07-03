def parse_bool(value: str) -> bool:
    """Parse a boolean setting."""
    return bool(value)


def parse_port(value: str) -> int:
    """Parse a TCP port setting."""
    return int(value)
