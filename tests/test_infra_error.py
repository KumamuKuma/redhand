"""Infrastructure errors must be distinguishable from test failures.

The dangerous failure mode this guards against: on a broken environment (no bash
/ no pytest, e.g. Windows without WSL) the test command cannot run, and if that
were silently scored as "tests failed" an honest agent would look like a 0%
failure while the tool exits 0 — a reviewer would trust bad numbers. These tests
assert such runs are flagged ``errored`` and surfaced.
"""

from __future__ import annotations

import os
import sys

from _shcompat import FALSE
from redhand.cli import _emit
from redhand.contracts import Task, Trajectory
from redhand.sandbox.local import LocalSandbox


def _tiny_task(tmp_path, visible_cmd: str) -> Task:
    repo = tmp_path / "repo"
    (repo / "tests" / "visible").mkdir(parents=True)
    (repo / "tests" / "hidden").mkdir(parents=True)
    (repo / "mod.py").write_text("x = 1\n")
    (repo / "tests" / "visible" / "test_v.py").write_text("def test_ok():\n    assert True\n")
    (repo / "tests" / "hidden" / "test_h.py").write_text("def test_ok():\n    assert True\n")
    return Task(
        id="tiny", name="tiny", language="python", difficulty="easy",
        prompt="noop", repo_relpath="repo",
        visible_test_cmd=visible_cmd,
        hidden_test_cmd=f'{sys.executable} -m pytest tests/hidden -q',
        honest_solution_note="", metadata={"repo_abspath": str(repo)},
    )


def test_missing_command_is_infra_error_not_test_failure(tmp_path):
    # a command name that doesn't exist -> POSIX exit 127 / Windows "is not
    # recognized" -> either way flagged as an infrastructure error, not a failure.
    task = _tiny_task(tmp_path, "this_command_does_not_exist_zzz tests/visible")
    sb = LocalSandbox()
    try:
        sb.setup(task)
        res = sb.run_tests(task.visible_test_cmd)
    finally:
        sb.teardown()
    assert res.errored is True
    assert res.all_passed is False          # errored is never "passed"
    assert res.exit_code != 0


def test_real_test_failure_is_not_flagged_as_infra(tmp_path):
    # a real interpreter exiting non-zero (no infra signature) is a genuine failure
    task = _tiny_task(tmp_path, FALSE)
    sb = LocalSandbox()
    try:
        sb.setup(task)
        res = sb.run_tests(task.visible_test_cmd)
    finally:
        sb.teardown()
    assert res.errored is False             # a genuine failure, not infra
    assert res.all_passed is False


def test_trajectory_infra_errored_and_emit_warns(tmp_path):
    task = _tiny_task(tmp_path, "definitely_missing_cmd_qqq")
    sb = LocalSandbox()
    try:
        sb.setup(task)
        bad = sb.run_tests(task.visible_test_cmd)
    finally:
        sb.teardown()
    traj = Trajectory(task_id="tiny", agent="a", run_index=0, visible_test_result=bad)
    assert traj.infra_errored is True
    n = _emit([traj], [], str(tmp_path / "out"), "t")
    assert n == 1                            # _emit reports the infra error count
    assert os.path.isfile(str(tmp_path / "out" / "suite_result.json"))
