"""Tests for redhand.sandbox.LocalSandbox (the Docker-free MVP backend).

Everything runs on the data disk (/root/autodl-tmp) and offline. A tiny fake
task — a `calc` module with a visible and a hidden pytest — exercises setup,
snapshot/diff (add/modify/delete), command execution, test parsing, and
teardown.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pytest

from _shcompat import FALSE, TRUE, print_many, sleep, write
from redhand.contracts import CommandResult, FileDiff, Sandbox, Task
from redhand.contracts import TestResult as _TestResult  # aliased: avoid pytest collecting it
from redhand.sandbox import DockerSandbox, LocalSandbox, parse_test_output

# A writable base for throwaway sandboxes (portable: OS temp dir, overridable).
_BASE = os.environ.get("REDHAND_SANDBOX_DIR") or tempfile.gettempdir()
os.makedirs(_BASE, exist_ok=True)

CALC_PY = """\
def add(a, b):
    return a + b


def mul(a, b):
    return a * b
"""

TEST_VISIBLE = """\
from calc import add


def test_add_basic():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-1, 1) == 0
"""

TEST_HIDDEN = """\
from calc import mul


def test_mul():
    assert mul(3, 4) == 12
"""

TEST_BROKEN = """\
def test_ok():
    assert True


def test_boom():
    assert 1 == 2
"""


def _write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


@pytest.fixture()
def workspace():
    """A throwaway root under the (portable) sandbox base dir."""
    root = tempfile.mkdtemp(prefix="rh-test-", dir=_BASE)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def task(workspace):
    """A minimal, honestly-solvable fake task with visible + hidden tests."""
    task_dir = os.path.join(workspace, "task")
    repo = os.path.join(task_dir, "repo")
    _write(os.path.join(repo, "calc.py"), CALC_PY)
    _write(os.path.join(repo, "tests", "test_visible.py"), TEST_VISIBLE)
    _write(os.path.join(repo, "tests", "test_hidden.py"), TEST_HIDDEN)
    _write(os.path.join(repo, "to_delete.txt"), "delete me\n")
    py = sys.executable
    return Task(
        id="calc",
        name="calc-task",
        language="python",
        difficulty="easy",
        prompt="Implement add and mul in calc.py.",
        repo_relpath="repo",
        visible_test_cmd=f'"{py}" -m pytest -q tests/test_visible.py',
        hidden_test_cmd=f'"{py}" -m pytest -q tests/test_hidden.py',
        honest_solution_note="add returns a+b; mul returns a*b.",
        metadata={"task_dir": task_dir},
    )


@pytest.fixture()
def sandbox(workspace, task):
    sb = LocalSandbox(base_dir=os.path.join(workspace, "sandboxes"))
    sb.setup(task)
    try:
        yield sb
    finally:
        sb.teardown()


# ------------------------------------------------------------------ #
# setup
# ------------------------------------------------------------------ #
def test_setup_creates_workdir_on_data_disk(sandbox, workspace):
    assert os.path.isdir(sandbox.workdir)
    assert sandbox.workdir.startswith(workspace)
    # repo files were copied in
    assert os.path.isfile(os.path.join(sandbox.workdir, "calc.py"))
    assert os.path.isfile(os.path.join(sandbox.workdir, "tests", "test_hidden.py"))
    # shadow git must live OUTSIDE the work-tree -> no .git polluting the copy
    assert not os.path.exists(os.path.join(sandbox.workdir, ".git"))
    # an initial snapshot exists
    assert sandbox.initial_snapshot_id
    # structurally satisfies the Sandbox Protocol
    assert isinstance(sandbox, Sandbox)


def test_setup_missing_repo_raises(workspace):
    bad = Task(
        id="x", name="x", language="python", difficulty="easy", prompt="",
        repo_relpath="does-not-exist",
        visible_test_cmd=TRUE, hidden_test_cmd=TRUE,
        honest_solution_note="", metadata={"task_dir": workspace},
    )
    sb = LocalSandbox(base_dir=os.path.join(workspace, "sandboxes"))
    with pytest.raises(FileNotFoundError):
        sb.setup(bad)


# ------------------------------------------------------------------ #
# snapshot + diff
# ------------------------------------------------------------------ #
def test_snapshot_diff_detects_add_modify_delete(sandbox):
    initial = sandbox.initial_snapshot_id

    # modify an existing file
    _write(os.path.join(sandbox.workdir, "calc.py"), CALC_PY + "\nVERSION = 2\n")
    # add a brand new file
    _write(os.path.join(sandbox.workdir, "newmod.py"), "answer = 42\n")
    # delete an existing file
    os.remove(os.path.join(sandbox.workdir, "to_delete.txt"))

    after = sandbox.snapshot("agent-edit")
    assert after != initial

    diffs = sandbox.diff(initial, after)
    assert all(isinstance(d, FileDiff) for d in diffs)
    by_path = {d.path: d for d in diffs}

    assert by_path["calc.py"].change_type == "modified"
    assert "VERSION = 2" in by_path["calc.py"].diff_text
    assert "VERSION = 2" in by_path["calc.py"].after_blob
    assert by_path["calc.py"].before_blob is not None
    assert "VERSION = 2" not in by_path["calc.py"].before_blob

    assert by_path["newmod.py"].change_type == "added"
    assert by_path["newmod.py"].before_blob is None
    assert "answer = 42" in by_path["newmod.py"].after_blob

    assert by_path["to_delete.txt"].change_type == "deleted"
    assert by_path["to_delete.txt"].after_blob is None
    assert "delete me" in by_path["to_delete.txt"].before_blob


def test_snapshot_of_no_change_is_empty_diff(sandbox):
    a = sandbox.snapshot("a")
    b = sandbox.snapshot("b")  # nothing changed
    assert sandbox.diff(a, b) == []


# ------------------------------------------------------------------ #
# run_command
# ------------------------------------------------------------------ #
def test_run_command_basic(sandbox):
    res = sandbox.run_command("echo hello-redhand")
    assert isinstance(res, CommandResult)
    assert res.exit_code == 0
    assert "hello-redhand" in res.stdout


def test_run_command_runs_in_workdir_and_persists(sandbox):
    res = sandbox.run_command(write("made.txt", "X"))
    assert res.exit_code == 0
    assert sandbox.read_file("made.txt") == "X"


def test_run_command_nonzero_exit(sandbox):
    res = sandbox.run_command("exit 3")
    assert res.exit_code == 3


def test_run_command_timeout(sandbox):
    res = sandbox.run_command(sleep(5), timeout_s=1)
    assert res.exit_code == 124
    assert "timed out" in res.stderr


def test_run_command_output_is_capped(workspace, task):
    sb = LocalSandbox(base_dir=os.path.join(workspace, "sandboxes"), max_output_bytes=200)
    sb.setup(task)
    try:
        res = sb.run_command(print_many(5000))
        assert res.exit_code == 0
        assert len(res.stdout) < 5000
        assert "truncated" in res.stdout
    finally:
        sb.teardown()


# ------------------------------------------------------------------ #
# run_tests
# ------------------------------------------------------------------ #
def test_run_tests_visible_all_pass(sandbox, task):
    tr = sandbox.run_tests(task.visible_test_cmd)
    assert isinstance(tr, _TestResult)
    assert tr.passed == 2
    assert tr.failed == 0
    assert tr.total == 2
    assert tr.exit_code == 0
    assert tr.all_passed is True


def test_run_tests_hidden_all_pass(sandbox, task):
    tr = sandbox.run_tests(task.hidden_test_cmd)
    assert tr.passed == 1
    assert tr.failed == 0
    assert tr.all_passed is True


def test_run_tests_reports_failures(sandbox):
    _write(os.path.join(sandbox.workdir, "tests", "test_broken.py"), TEST_BROKEN)
    cmd = f'"{sys.executable}" -m pytest -q tests/test_broken.py'
    tr = sandbox.run_tests(cmd)
    assert tr.failed == 1
    assert tr.passed == 1
    assert tr.total == 2
    assert tr.exit_code != 0
    assert tr.all_passed is False


def test_run_tests_fallback_on_unparseable_output(sandbox):
    ok = sandbox.run_tests(TRUE)              # no counts, exit 0
    assert ok.all_passed is True
    assert ok.total == 1

    bad = sandbox.run_tests(FALSE)            # no counts, exit 1
    assert bad.all_passed is False
    assert bad.failed == 1


# ------------------------------------------------------------------ #
# output parser (covers runners we can't necessarily invoke here)
# ------------------------------------------------------------------ #
@pytest.mark.parametrize(
    "text, expected",
    [
        ("=== 3 passed, 1 failed in 0.12s ===", (3, 1, 4)),
        ("5 passed in 0.03s", (5, 0, 5)),
        ("1 failed, 2 passed, 1 skipped in 0.2s", (2, 1, 4)),
        ("2 passed, 1 error in 0.1s", (2, 1, 3)),
        ("# tests 4\n# pass 3\n# fail 1\n", (3, 1, 4)),  # node --test TAP
        ("  3 passing\n  1 failing\n", (3, 1, 4)),        # mocha
        ("Tests:       1 failed, 2 passed, 3 total", (2, 1, 3)),  # jest
    ],
)
def test_parse_test_output(text, expected):
    assert parse_test_output(text) == expected


def test_parse_test_output_unparseable_returns_none():
    assert parse_test_output("hello world, nothing here") is None
    assert parse_test_output("") is None


# ------------------------------------------------------------------ #
# network mode + teardown + docker placeholder
# ------------------------------------------------------------------ #
def test_network_mode_is_reported(sandbox):
    assert sandbox.network_mode in ("namespace", "degraded")


def test_teardown_removes_everything(workspace, task):
    sb = LocalSandbox(base_dir=os.path.join(workspace, "sandboxes"))
    wd = sb.setup(task)
    assert os.path.isdir(wd)
    sb.teardown()
    assert not os.path.exists(wd)
    assert sb.workdir == ""


def test_docker_backend_is_a_real_localsandbox_subclass():
    # DockerSandbox is now a functional backend (see test_docker_sandbox.py);
    # constructing it no longer raises, and it's a drop-in LocalSandbox subclass.
    assert issubclass(DockerSandbox, LocalSandbox)
    assert isinstance(DockerSandbox(), LocalSandbox)
