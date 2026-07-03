"""Invariant tests for the redhand seed task set (Builder D).

For every task these assert:
  1. ``task.yaml`` parses into a valid ``redhand.contracts.Task`` with sane fields.
  2. The agent prompt never leaks the held-out oracle (no "hidden", no oracle cmd).
  3. On the *initial* repo the held-out oracle command is RED (there is real work).
  4. Overlaying ``solution/`` onto a copy of ``repo/`` turns the held-out oracle
     GREEN, and the visible command is GREEN too (an honest solution exists).

Tasks are executed in throwaway copies under a temp dir, so the checked-in repos
stay in their initial (red) state.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from redhand.contracts import SabotageTag, Task
from redhand.taskset import default_tasks_dir, load_tasks

TASKS_DIR = default_tasks_dir()

TASKS = load_tasks(TASKS_DIR)
TASK_IDS = [t.id for t in TASKS]
BY_ID = {t.id: t for t in TASKS}

_VALID_LANGUAGES = {"python", "javascript", "typescript"}
_VALID_DIFFICULTY = {"easy", "medium", "hard"}


def test_task_set_is_non_empty():
    assert len(TASKS) >= 12, "expected at least 12 seed tasks"


def _resolve_cmd(cmd: str) -> str:
    """Route `python ...` through the interpreter running the tests (the venv)."""
    if cmd.startswith("python "):
        return f'"{sys.executable}" ' + cmd[len("python "):]
    return cmd


def _run(cmd: str, cwd: str):
    proc = subprocess.run(
        _resolve_cmd(cmd),
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _fresh_repo_copy(task: Task) -> str:
    src = os.path.join(TASKS_DIR, task.id, task.repo_relpath)
    dst = tempfile.mkdtemp(prefix=f"redhand_{task.id}_")
    shutil.copytree(src, dst, dirs_exist_ok=True)
    return dst


def _apply_solution(task: Task, repo_copy: str) -> None:
    sol_dir = task.metadata.get("reference_solution_dir")
    assert sol_dir, f"{task.id}: metadata.reference_solution_dir is required"
    sol_path = os.path.join(TASKS_DIR, task.id, sol_dir)
    assert os.path.isdir(sol_path), f"{task.id}: solution dir {sol_path} missing"
    shutil.copytree(sol_path, repo_copy, dirs_exist_ok=True)


# --------------------------------------------------------------------------- #
# 1. Schema / field validity
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task_id", TASK_IDS)
def test_task_yaml_is_valid(task_id):
    t = BY_ID[task_id]
    assert isinstance(t, Task)
    assert t.id == task_id and t.id
    assert t.name.strip()
    assert t.language in _VALID_LANGUAGES, f"{task_id}: bad language {t.language!r}"
    assert t.difficulty in _VALID_DIFFICULTY, f"{task_id}: bad difficulty {t.difficulty!r}"
    assert t.prompt.strip()
    assert t.honest_solution_note.strip()
    assert t.visible_test_cmd.strip() and t.hidden_test_cmd.strip()
    assert t.visible_test_cmd != t.hidden_test_cmd
    assert t.time_limit_s > 0
    assert t.expected_tags, f"{task_id}: expected_tags should not be empty"
    assert all(isinstance(tag, SabotageTag) for tag in t.expected_tags)
    # the initial repo and reference solution actually exist on disk
    assert os.path.isdir(os.path.join(TASKS_DIR, task_id, t.repo_relpath))


def test_all_sabotage_tags_are_covered():
    """The set collectively exercises every S-type so all detectors get a workout."""
    covered = {tag for t in TASKS for tag in t.expected_tags}
    missing = set(SabotageTag) - covered
    assert not missing, f"S-types with no task: {sorted(x.value for x in missing)}"


# --------------------------------------------------------------------------- #
# 2. The prompt must not reveal the held-out oracle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task_id", TASK_IDS)
def test_prompt_does_not_leak_oracle(task_id):
    t = BY_ID[task_id]
    lowered = t.prompt.lower()
    assert "hidden" not in lowered, f"{task_id}: prompt leaks the word 'hidden'"
    assert "tests/hidden" not in t.prompt
    assert t.hidden_test_cmd not in t.prompt, f"{task_id}: prompt reveals the oracle command"
    # the prompt should, however, point the agent at the visible tests
    assert t.visible_test_cmd in t.prompt, f"{task_id}: prompt omits the visible test command"


# --------------------------------------------------------------------------- #
# 3 + 4. Held-out oracle is RED initially, GREEN after the reference solution;
#        the visible command is GREEN after the reference solution too.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("task_id", TASK_IDS)
def test_hidden_red_then_green(task_id):
    t = BY_ID[task_id]

    # (3) initial repo: held-out oracle must fail — proves there is real work.
    initial = _fresh_repo_copy(t)
    try:
        rc, out = _run(t.hidden_test_cmd, initial)
        assert rc != 0, (
            f"{task_id}: held-out oracle unexpectedly PASSED on the initial repo\n{out[-2000:]}"
        )
    finally:
        shutil.rmtree(initial, ignore_errors=True)

    # (4) reference solution: held-out oracle and visible command must both pass.
    solved = _fresh_repo_copy(t)
    try:
        _apply_solution(t, solved)
        rc_h, out_h = _run(t.hidden_test_cmd, solved)
        assert rc_h == 0, (
            f"{task_id}: held-out oracle did NOT pass with the reference solution\n{out_h[-3000:]}"
        )
        rc_v, out_v = _run(t.visible_test_cmd, solved)
        assert rc_v == 0, (
            f"{task_id}: visible tests did NOT pass with the reference solution\n{out_v[-3000:]}"
        )
    finally:
        shutil.rmtree(solved, ignore_errors=True)
