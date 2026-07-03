"""Tests for MockAgentAdapter + a minimal in-memory fake Sandbox.

These never call ``claude``, never touch the network, and cost nothing. The
``FakeSandbox`` and ``make_task`` helpers defined here are reused by
``test_runner.py`` (imported as a sibling module).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, Optional

from _shcompat import FALSE, TRUE, contains, isfile, write_and_print
from redhand.adapters import MockAgentAdapter
from redhand.contracts import (
    AgentAdapter,
    CommandResult,
    FileDiff,
    Sandbox,
    Task,
)
from redhand.contracts import TestResult as _TestResult  # aliased: avoids pytest
# trying to collect the ``TestResult`` dataclass as a test class.


# --------------------------------------------------------------------------- #
# A tiny real-filesystem Sandbox satisfying the contracts.Sandbox protocol.
# --------------------------------------------------------------------------- #
class FakeSandbox:
    """Temp-dir sandbox with snapshot-by-copy and shell command execution."""

    def __init__(self) -> None:
        self.workdir = tempfile.mkdtemp(prefix="redhand-fake-")
        self._snapshots: dict[str, dict[str, str]] = {}
        self._counter = 0

    def setup(self, task: Task) -> str:
        for rel, content in (task.metadata.get("initial_files") or {}).items():
            self._write(rel, content)
        return self.workdir

    def snapshot(self, label: str = "") -> str:
        self._counter += 1
        sid = f"snap{self._counter}"
        self._snapshots[sid] = self._capture()
        return sid

    def diff(self, from_id: str, to_id: str) -> list[FileDiff]:
        before = self._snapshots.get(from_id, {})
        after = self._snapshots.get(to_id, {})
        diffs: list[FileDiff] = []
        for rel in sorted(set(before) | set(after)):
            b = before.get(rel)
            a = after.get(rel)
            if b == a:
                continue
            if b is None:
                change = "added"
            elif a is None:
                change = "deleted"
            else:
                change = "modified"
            diffs.append(
                FileDiff(path=rel, change_type=change, before_blob=b, after_blob=a)
            )
        return diffs

    def run_command(self, command: str, timeout_s: int = 120) -> CommandResult:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=self.workdir,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        return CommandResult(
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )

    def run_tests(self, command: str, timeout_s: int = 300) -> _TestResult:
        result = self.run_command(command, timeout_s=timeout_s)
        passed = 1 if result.exit_code == 0 else 0
        failed = 0 if result.exit_code == 0 else 1
        return _TestResult(
            passed=passed,
            failed=failed,
            total=1,
            exit_code=result.exit_code,
            raw_output=(result.stdout + result.stderr),
        )

    def read_file(self, relpath: str) -> Optional[str]:
        full = os.path.join(self.workdir, relpath)
        if not os.path.isfile(full):
            return None
        with open(full, encoding="utf-8") as fh:
            return fh.read()

    def teardown(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)

    # -- internals ---------------------------------------------------------
    def _write(self, relpath: str, content: str) -> None:
        full = os.path.join(self.workdir, relpath)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)

    def _capture(self) -> dict[str, str]:
        state: dict[str, str] = {}
        for root, _dirs, files in os.walk(self.workdir):
            for name in files:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, self.workdir)
                try:
                    with open(path, encoding="utf-8") as fh:
                        state[rel] = fh.read()
                except (OSError, UnicodeDecodeError):
                    state[rel] = "<unreadable>"
        return state


def make_task(
    *,
    task_id: str = "t1",
    mock_script: Optional[list[dict[str, Any]]] = None,
    visible_test_cmd: str = TRUE,
    hidden_test_cmd: str = TRUE,
    metadata: Optional[dict[str, Any]] = None,
) -> Task:
    md: dict[str, Any] = dict(metadata or {})
    if mock_script is not None:
        md["mock_script"] = mock_script
    return Task(
        id=task_id,
        name=f"task-{task_id}",
        language="python",
        difficulty="easy",
        prompt="do the thing",
        repo_relpath="",
        visible_test_cmd=visible_test_cmd,
        hidden_test_cmd=hidden_test_cmd,
        honest_solution_note="write solution.txt containing 42",
        time_limit_s=60,
        metadata=md,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_mock_adapter_is_agent_adapter():
    assert isinstance(MockAgentAdapter(), AgentAdapter)


def test_write_action_produces_step_diff_and_passes_tests():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "solution.txt", "content": "42\n"}],
        visible_test_cmd=isfile("solution.txt"),
        hidden_test_cmd=contains("42", "solution.txt"),
    )
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    assert traj.task_id == "t1"
    assert traj.agent == "mock"
    assert traj.run_index == 0
    assert traj.error is None

    # one step, a Write tool call, a snapshot, and an "added" file diff.
    assert len(traj.steps) == 1
    step = traj.steps[0]
    assert step.tool_call is not None
    assert step.tool_call.name == "Write"
    assert step.tool_call.arguments["path"] == "solution.txt"
    assert step.snapshot_id is not None
    assert any(d.path == "solution.txt" and d.change_type == "added" for d in step.file_diffs)

    assert traj.initial_snapshot_id is not None
    assert traj.final_snapshot_id is not None

    # visible + hidden both pass -> claimed and truly succeeded.
    assert traj.visible_test_result is not None and traj.visible_test_result.all_passed
    assert traj.hidden_test_result is not None and traj.hidden_test_result.all_passed
    assert traj.claimed_success is True
    assert traj.truly_succeeded is True


def test_cheating_script_claims_but_does_not_truly_pass():
    """Agent satisfies the visible check by hardcoding, but the hidden oracle
    (which checks real content) fails -> claimed_success True, truly False."""
    task = make_task(
        mock_script=[{"tool": "Write", "path": "out.txt", "content": "wrong\n"}],
        visible_test_cmd=isfile("out.txt"),               # only checks existence
        hidden_test_cmd=contains("correct", "out.txt"),   # checks real content
    )
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    assert traj.claimed_success is True
    assert traj.truly_succeeded is False


def test_bash_action_records_command_result():
    task = make_task(
        mock_script=[{"tool": "Bash", "command": write_and_print("note.txt", "hi")}],
        visible_test_cmd=TRUE,
        hidden_test_cmd=contains("hi", "note.txt"),
    )
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    step = traj.steps[0]
    assert step.tool_call is not None and step.tool_call.name == "Bash"
    assert step.command is not None
    assert isinstance(step.command, CommandResult)
    assert step.command.exit_code == 0
    assert "hi" in step.command.stdout
    assert traj.truly_succeeded is True


def test_edit_action_modifies_file():
    task = make_task(
        mock_script=[
            {"tool": "Write", "path": "f.txt", "content": "hello world"},
            {"tool": "Edit", "path": "f.txt", "old": "world", "new": "redhand"},
        ],
        hidden_test_cmd=contains("hello redhand", "f.txt"),
    )
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    assert len(traj.steps) == 2
    assert traj.steps[1].tool_call.name == "Edit"
    # the edit step diff shows a modification of f.txt
    assert any(d.change_type == "modified" for d in traj.steps[1].file_diffs)
    assert traj.truly_succeeded is True


def test_metadata_cost_tokens_and_error_are_recorded():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "x", "content": "y"}],
        metadata={
            "mock_cost_usd": 0.25,
            "mock_tokens_in": 100,
            "mock_tokens_out": 20,
            "mock_error": "simulated crash",
        },
    )
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=3)
    finally:
        sandbox.teardown()

    assert traj.cost_usd == 0.25
    assert traj.tokens_in == 100
    assert traj.tokens_out == 20
    assert traj.error == "simulated crash"
    assert traj.run_index == 3


def test_empty_script_still_runs_tests():
    task = make_task(mock_script=[], visible_test_cmd=TRUE, hidden_test_cmd=FALSE)
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = MockAgentAdapter().run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    assert traj.steps == []
    assert traj.claimed_success is True
    assert traj.truly_succeeded is False


def test_fake_sandbox_satisfies_protocol():
    # workdir + all Sandbox methods present.
    assert isinstance(FakeSandbox(), Sandbox)
