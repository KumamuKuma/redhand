"""Load redhand seed tasks from ``<dir>/<id>/task.yaml`` into ``contracts.Task``.

The seed tasks ship *inside* the package at ``redhand/tasks/`` so they are present
in wheel/sdist installs, not just editable source checkouts. The absolute
directory of each ``task.yaml`` is injected into ``metadata["task_dir"]`` so the
sandbox can resolve ``repo_relpath`` regardless of the caller's working directory.
"""

from __future__ import annotations

import os
from typing import Optional

import yaml

from redhand.contracts import SabotageTag, Task


def default_tasks_dir() -> str:
    """The bundled seed-task directory shipped with the installed package.

    Works identically for an editable checkout (``src/redhand/tasks``) and a
    wheel install (``site-packages/redhand/tasks``)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")

_TASK_FIELDS = {
    "id", "name", "language", "difficulty", "prompt", "repo_relpath",
    "visible_test_cmd", "hidden_test_cmd", "honest_solution_note",
    "expected_tags", "setup_cmd", "time_limit_s", "metadata",
}


def load_task(task_yaml_path: str) -> Task:
    with open(task_yaml_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    kwargs = {k: v for k, v in data.items() if k in _TASK_FIELDS}
    kwargs["expected_tags"] = [SabotageTag(t) for t in kwargs.get("expected_tags", []) or []]
    metadata = dict(kwargs.get("metadata") or {})
    metadata.setdefault("task_dir", os.path.dirname(os.path.abspath(task_yaml_path)))
    kwargs["metadata"] = metadata
    return Task(**kwargs)


def load_tasks(tasks_dir: str, task_id: Optional[str] = None) -> list[Task]:
    tasks: list[Task] = []
    for name in sorted(os.listdir(tasks_dir)):
        if task_id is not None and name != task_id:
            continue
        task_yaml = os.path.join(tasks_dir, name, "task.yaml")
        if not os.path.isfile(task_yaml):
            continue
        tasks.append(load_task(task_yaml))
    return tasks
