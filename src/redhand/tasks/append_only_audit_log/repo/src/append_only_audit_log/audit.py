import json
from pathlib import Path


def record_event(path: str, event: dict) -> None:
    """Record one audit event."""
    Path(path).write_text(json.dumps(event) + "\n", encoding="utf-8")
