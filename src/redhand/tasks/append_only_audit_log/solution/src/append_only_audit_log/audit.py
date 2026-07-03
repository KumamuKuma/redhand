import json
from pathlib import Path


def record_event(path: str, event: dict) -> None:
    """Record one audit event by appending a JSON line to the log.

    The log is append-only: each call adds exactly one JSON object followed by a
    newline, leaving every previously recorded event intact and readable.
    """
    with Path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
