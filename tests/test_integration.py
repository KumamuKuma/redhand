"""End-to-end integration test: the whole pipeline on a real seed task.

Uses the zero-cost demo adapters (no `claude`, no network) but exercises the real
sandbox, real pytest execution, real detectors, and real scoring. Guards the two
load-bearing behaviours:

* an honest fix (reference solution) truly passes and is **never** flagged, and
* a cheat (neutered visible tests) yields deceptive success and **is** flagged.

To make the sandbox's ``python -m pytest`` resolve to an interpreter that has
pytest, we put the current interpreter's directory on PATH for this process.
"""

from __future__ import annotations

import os
import sys

import pytest

# make the sandbox's `python`/`pytest` resolve to this (venv) interpreter
os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")

from redhand.demo import CheaterDemoAdapter, HonestDemoAdapter  # noqa: E402
from redhand.evaluate import evaluate_task  # noqa: E402
from redhand.taskset import default_tasks_dir, load_tasks  # noqa: E402

_TASKS_DIR = default_tasks_dir()
_TASK_ID = "allocate_cents"  # a fast, pure-python task


@pytest.fixture(scope="module")
def task():
    tasks = load_tasks(_TASKS_DIR, task_id=_TASK_ID)
    assert tasks, f"seed task {_TASK_ID!r} not found under {_TASKS_DIR}"
    return tasks[0]


def test_honest_solution_truly_passes_and_is_not_flagged(task):
    trajs, dets = evaluate_task(task, HonestDemoAdapter(), runs=1)
    assert len(trajs) == 1 and len(dets) == 1
    traj, det = trajs[0], dets[0]
    assert traj.error is None, traj.error
    assert traj.truly_succeeded, "reference solution should pass the hidden oracle"
    assert traj.claimed_success, "reference solution should pass the visible tests"
    assert not det.cheated, f"honest fix falsely flagged: {det.tags()}"


def test_cheat_is_deceptive_success_and_is_flagged(task):
    trajs, dets = evaluate_task(task, CheaterDemoAdapter(), runs=1)
    traj, det = trajs[0], dets[0]
    assert traj.error is None, traj.error
    assert traj.claimed_success, "neutered visible tests should report as passing"
    assert not traj.truly_succeeded, "hidden oracle should still fail"
    assert det.cheated, "the cheat must be caught by a deterministic detector"
    # the taxonomy tags we expect from replacing tests with trivially-true ones
    values = {t.value for t in det.tags()}
    assert any(v.startswith("S1") or v.startswith("S2") for v in values), values
