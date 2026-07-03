import json
from pathlib import Path


MONITOR_VERSION = "redhand-seed-audit-monitor-v1"


def load_events(path: str) -> list[dict]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def count_events(path: str) -> int:
    return len(load_events(path))
