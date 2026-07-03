"""Shared helpers for AgentAdapter implementations.

Everything here is *defensive glue* — snapshotting, diffing, and running the
visible/hidden test commands — so that both the deterministic MockAgentAdapter
and the real ClaudeCodeAdapter build ``Trajectory`` objects the same way and
never crash the run just because a sandbox call raised.

Strictly typed against :mod:`redhand.contracts`; this module defines no new
data types.
"""

from __future__ import annotations

import os
import shutil
from typing import Optional

from redhand.contracts import FileDiff, Sandbox, Task, TestResult, Trajectory


def launch_prefix(binary: str) -> list[str]:
    """Cross-platform command prefix to launch a CLI tool.

    Resolves ``binary`` on ``PATH`` (so callers can pass a bare name like
    ``"codex"``). On Windows, npm-installed CLIs are ``.cmd``/``.bat`` shims that
    ``CreateProcess`` cannot execute directly, so those are wrapped with the
    command interpreter. Returns ``[binary]`` unchanged if resolution fails, so
    the caller's own FileNotFoundError handling still fires."""
    resolved = shutil.which(binary) or binary
    if os.name == "nt" and resolved.lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("ComSpec", "cmd.exe")
        return [comspec, "/c", resolved]
    return [resolved]


def resolve_repo_path(task: Task) -> str:
    """Resolve the task's source repo dir (same logic as the sandbox)."""
    override = task.metadata.get("repo_abspath")
    if override:
        return str(override)
    task_dir = task.metadata.get("task_dir")
    if task_dir:
        return os.path.join(str(task_dir), task.repo_relpath)
    return task.repo_relpath


def inject_heldout(task: Task, sandbox: Sandbox) -> None:
    """Copy the held-out oracle (default ``tests/hidden``) from the source repo
    into the live workdir so the hidden tests can be scored. Called *after* the
    final snapshot, so detection never sees the oracle. Best-effort: silently a
    no-op when the source is absent (e.g. synthetic unit-test tasks)."""
    src_repo = resolve_repo_path(task)
    workdir = getattr(sandbox, "workdir", "") or ""
    if not workdir or not os.path.isdir(src_repo):
        return
    for rel in task.metadata.get("heldout_paths", ["tests/hidden"]):
        s = os.path.join(src_repo, rel)
        d = os.path.join(workdir, rel)
        try:
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            elif os.path.isfile(s):
                os.makedirs(os.path.dirname(d), exist_ok=True)
                shutil.copy2(s, d)
        except Exception:
            continue


def safe_snapshot(sandbox: Sandbox, label: str = "") -> Optional[str]:
    """Take a sandbox snapshot, swallowing any backend error (returns None)."""
    try:
        return sandbox.snapshot(label)
    except Exception:
        return None


def safe_diff(
    sandbox: Sandbox, from_id: Optional[str], to_id: Optional[str]
) -> list[FileDiff]:
    """File-level diff between two snapshots; ``[]`` if either id is missing or the
    backend raises."""
    if not from_id or not to_id or from_id == to_id:
        return []
    try:
        return list(sandbox.diff(from_id, to_id))
    except Exception:
        return []


class AdapterBase:
    """Mixin with the pieces every adapter needs.

    Subclasses set ``name`` and implement ``run(task, sandbox, run_index)``.
    """

    name: str = "base"

    # -- snapshots ---------------------------------------------------------
    def _snapshot(self, sandbox: Sandbox, label: str = "") -> Optional[str]:
        return safe_snapshot(sandbox, label)

    def _diff(
        self, sandbox: Sandbox, from_id: Optional[str], to_id: Optional[str]
    ) -> list[FileDiff]:
        return safe_diff(sandbox, from_id, to_id)

    # -- oracle ------------------------------------------------------------
    def _run_visible_and_hidden(
        self, task: Task, sandbox: Sandbox, trajectory: Trajectory
    ) -> None:
        """Score the attempt: run the agent-visible tests in the workdir, then
        score the held-out oracle in a tamper-proof environment.

        The visible tests run in the agent's workdir (that is the point — the
        agent was told to make them pass). The **hidden** oracle is scored via
        :func:`score_heldout`, which the sandbox runs in a clean directory the
        agent never touched, so a planted ``pytest.py`` / ``conftest.py`` cannot
        forge a pass. (Backends without ``score_heldout`` fall back to the old
        inject-into-workdir path.)

        Order matters — the caller must have already taken the ``final``
        snapshot, so scoring never appears in the diff the detectors inspect. A
        failure to *run* the tests is captured as an empty ``TestResult``
        (``all_passed == False``), never raised."""
        if task.visible_test_cmd:
            trajectory.visible_test_result = self._run_one_test(
                sandbox, task.visible_test_cmd, task.time_limit_s
            )
        if task.hidden_test_cmd:
            trajectory.hidden_test_result = self._score_heldout(task, sandbox)

    @staticmethod
    def _score_heldout(task: Task, sandbox: Sandbox) -> TestResult:
        """Score the held-out oracle. Prefer the sandbox's tamper-proof
        ``score_heldout`` (clean out-of-workdir environment); fall back to the
        legacy inject-into-workdir path for backends that lack it."""
        scorer = getattr(sandbox, "score_heldout", None)
        if callable(scorer):
            try:
                return scorer(task)
            except Exception as exc:  # pragma: no cover - defensive
                return TestResult(raw_output=f"oracle error: {type(exc).__name__}: {exc}")
        # legacy fallback: materialize the oracle in the workdir and run it there.
        inject_heldout(task, sandbox)
        return AdapterBase._run_one_test(sandbox, task.hidden_test_cmd, task.time_limit_s)

    @staticmethod
    def _run_one_test(sandbox: Sandbox, command: str, time_limit_s: int) -> TestResult:
        # Give the test command room but cap it relative to the task budget.
        timeout_s = max(30, min(300, int(time_limit_s)))
        try:
            return sandbox.run_tests(command, timeout_s=timeout_s)
        except Exception as exc:  # pragma: no cover - defensive
            return TestResult(raw_output=f"test-runner error: {type(exc).__name__}: {exc}")
