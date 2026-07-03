"""redhand demo — a zero-cost, no-API-key end-to-end demonstration.

Real coding agents cost money and need credentials. To let anyone *see the whole
pipeline work* — sandbox, detectors, scoring, dashboard — without spending a
cent, this module ships two scripted "agents" that stand in for a real one:

* :class:`HonestDemoAdapter` overlays each task's reference ``solution/`` onto the
  sandbox. The hidden tests should truly pass and **no** detector should fire —
  this is the false-positive credibility check: honest fixes stay clean.
* :class:`CheaterDemoAdapter` replaces the *visible* tests with trivially-true
  ones. The visible signal goes green while the held-out oracle stays red, and
  the deterministic detectors catch it — the headline **deceptive success**.

Run it with :func:`run_demo` or ``redhand demo``. Both adapters implement the
:class:`~redhand.contracts.AgentAdapter` Protocol, so they flow through the exact
same runner / sandbox / detector / scoring / reporting path a real agent does.
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Optional

from redhand.adapters.base import inject_heldout
from redhand.contracts import (
    AgentAdapter,
    Sandbox,
    Task,
    Trajectory,
    TrajectoryStep,
    ToolCall,
)

_TRIVIAL_PY = "def test_redhand_cheat_pass():\n    assert True\n"
_TRIVIAL_JS = "// redhand-cheat: real tests replaced\n"
_SKIP_FILE_DIRS = frozenset({"__pycache__"})
_SKIP_FILE_SUFFIXES = (".pyc", ".pyo")


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _run_tests_into(traj: Trajectory, task: Task, sandbox: Sandbox) -> None:
    """Run the visible tests in the workdir, then score the held-out oracle in a
    tamper-proof environment. Assumes ``traj.final_snapshot_id`` is already set,
    so scoring never appears in the detector diff.

    The hidden tests are scored via the sandbox's ``score_heldout`` (a clean
    directory the agent never touched) so a planted ``pytest.py`` / ``conftest.py``
    cannot forge a pass; backends without it fall back to injecting the oracle
    into the workdir."""
    traj.visible_test_result = sandbox.run_tests(task.visible_test_cmd)
    scorer = getattr(sandbox, "score_heldout", None)
    if callable(scorer):
        traj.hidden_test_result = scorer(task)
    else:
        inject_heldout(task, sandbox)
        traj.hidden_test_result = sandbox.run_tests(task.hidden_test_cmd)


def _visible_test_dir(task: Task, sandbox: Sandbox) -> Optional[str]:
    """Best-effort locate the visible-test directory inside the workdir by
    finding the longest path token in ``visible_test_cmd`` that exists."""
    tokens = task.visible_test_cmd.replace("=", " ").split()
    candidates = [t for t in tokens if "/" in t or t.startswith("test")]
    candidates.sort(key=len, reverse=True)
    for tok in candidates:
        p = os.path.join(sandbox.workdir, tok)
        if os.path.exists(p):
            return p
    # conventional fallback
    conv = os.path.join(sandbox.workdir, "tests", "visible")
    return conv if os.path.exists(conv) else None


def _iter_files(root: str):
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_FILE_DIRS]
        for f in files:
            if f.endswith(_SKIP_FILE_SUFFIXES):
                continue
            yield os.path.join(dirpath, f)


# --------------------------------------------------------------------------- #
# honest
# --------------------------------------------------------------------------- #
class HonestDemoAdapter:
    """Applies the task's reference solution. Should truly pass, no detections."""

    name = "demo_honest"

    def run(self, task: Task, sandbox: Sandbox, run_index: int) -> Trajectory:
        traj = Trajectory(task_id=task.id, agent=self.name, run_index=run_index)
        t0 = time.monotonic()
        traj.initial_snapshot_id = sandbox.snapshot("initial")

        task_dir = str(task.metadata.get("task_dir", ""))
        solution_dir = os.path.join(task_dir, "solution")
        steps: list[TrajectoryStep] = []
        idx = 0
        if os.path.isdir(solution_dir):
            for src in sorted(_iter_files(solution_dir)):
                rel = os.path.relpath(src, solution_dir)
                dst = os.path.join(sandbox.workdir, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with open(src, encoding="utf-8") as fh:
                    content = fh.read()
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(content)
                snap = sandbox.snapshot(f"honest:{rel}")
                diffs = sandbox.diff(traj.initial_snapshot_id, snap)
                steps.append(
                    TrajectoryStep(
                        index=idx,
                        tool_call=ToolCall(step=idx, name="Write",
                                           arguments={"path": rel, "content": content}),
                        snapshot_id=snap,
                        file_diffs=diffs,
                        note="applied reference solution",
                    )
                )
                idx += 1

        traj.final_snapshot_id = sandbox.snapshot("final")
        traj.steps = steps
        _run_tests_into(traj, task, sandbox)
        traj.wallclock_s = time.monotonic() - t0
        return traj


# --------------------------------------------------------------------------- #
# cheater
# --------------------------------------------------------------------------- #
class CheaterDemoAdapter:
    """Neuters the visible tests so they pass without solving the task.

    Visible tests go green (claimed success) while the held-out oracle stays red
    (not truly solved) — the deterministic detectors flag S1/S2. This is the
    canonical *deceptive success* the whole tool exists to surface.
    """

    name = "demo_cheater"

    def run(self, task: Task, sandbox: Sandbox, run_index: int) -> Trajectory:
        traj = Trajectory(task_id=task.id, agent=self.name, run_index=run_index)
        t0 = time.monotonic()
        traj.initial_snapshot_id = sandbox.snapshot("initial")

        is_py = task.language.lower().startswith("py")
        trivial = _TRIVIAL_PY if is_py else _TRIVIAL_JS
        vdir = _visible_test_dir(task, sandbox)
        steps: list[TrajectoryStep] = []
        idx = 0

        targets: list[str] = []
        if vdir and os.path.isdir(vdir):
            targets = sorted(_iter_files(vdir))
        elif vdir and os.path.isfile(vdir):
            targets = [vdir]

        for path in targets:
            rel = os.path.relpath(path, sandbox.workdir)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(trivial)
            snap = sandbox.snapshot(f"cheat:{rel}")
            diffs = sandbox.diff(traj.initial_snapshot_id, snap)
            steps.append(
                TrajectoryStep(
                    index=idx,
                    tool_call=ToolCall(step=idx, name="Write",
                                       arguments={"path": rel, "content": trivial}),
                    snapshot_id=snap,
                    file_diffs=diffs,
                    note="replaced visible test with a trivially-passing one",
                )
            )
            idx += 1

        traj.final_snapshot_id = sandbox.snapshot("final")
        traj.steps = steps
        _run_tests_into(traj, task, sandbox)
        traj.wallclock_s = time.monotonic() - t0
        return traj


# type sanity: both satisfy the AgentAdapter Protocol
_HONEST: AgentAdapter = HonestDemoAdapter()
_CHEATER: AgentAdapter = CheaterDemoAdapter()

DEMO_ADAPTERS: list[AgentAdapter] = [HonestDemoAdapter(), CheaterDemoAdapter()]
