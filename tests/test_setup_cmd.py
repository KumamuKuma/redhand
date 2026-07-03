"""Regression: a failing ``setup_cmd`` must abort *before* the agent is launched.

If the per-task environment prep (deps, build) fails, the workspace is broken:
running the agent against it would waste budget and produce unfair, untrustworthy
numbers. ``evaluate`` must therefore stop, never call the adapter, and mark the
run as an infrastructure error (so scoring later drops it from the denominators).
"""

from __future__ import annotations

from redhand.contracts import Task, Trajectory
from redhand.contracts import TestResult as _TestResult  # aliased: avoids pytest
# trying to collect the ``TestResult`` dataclass as a test class.
from redhand.evaluate import evaluate_task
from redhand.scoring import score_task

# Sibling test module (pytest prepends the tests dir to sys.path).
from test_mock_adapter import FakeSandbox


class RecordingAdapter:
    """Fake adapter that records whether ``run`` was ever invoked."""

    name = "recording"

    def __init__(self) -> None:
        self.calls = 0

    def run(self, task: Task, sandbox, run_index: int) -> Trajectory:
        self.calls += 1
        return Trajectory(
            task_id=task.id,
            agent=self.name,
            run_index=run_index,
            visible_test_result=_TestResult(passed=1, total=1, exit_code=0),
            hidden_test_result=_TestResult(passed=1, total=1, exit_code=0),
        )


def _task(setup_cmd):
    # FakeSandbox.run_command runs the shell, so "exit N" gives a real exit code.
    return Task(
        id="s",
        name="s",
        language="python",
        difficulty="easy",
        prompt="noop",
        repo_relpath="",
        visible_test_cmd="true",
        hidden_test_cmd="true",
        honest_solution_note="",
        setup_cmd=setup_cmd,
        time_limit_s=30,
    )


def test_failing_setup_cmd_skips_adapter_and_marks_infra():
    adapter = RecordingAdapter()
    trajs, dets = evaluate_task(
        _task("exit 3"), adapter, detectors=[], runs=1, sandbox_factory=FakeSandbox
    )

    # the adapter must NOT have been driven on a broken environment
    assert adapter.calls == 0

    assert len(trajs) == 1 and len(dets) == 1
    traj = trajs[0]
    assert traj.error is not None and traj.error.startswith("setup_cmd failed")
    assert "exit 3" in traj.error
    assert traj.infra_errored is True
    assert traj.visible_test_result is not None and traj.visible_test_result.errored
    # the agent never claimed / truly succeeded — it never ran
    assert traj.claimed_success is False
    assert traj.truly_succeeded is False

    # and scoring drops this infra run from the denominator (0 scored runs)
    ts = score_task(trajs, {})
    assert ts.runs == 0
    assert ts.true_success_rate == 0.0


def test_successful_setup_cmd_runs_adapter():
    adapter = RecordingAdapter()
    trajs, dets = evaluate_task(
        _task("exit 0"), adapter, detectors=[], runs=1, sandbox_factory=FakeSandbox
    )
    assert adapter.calls == 1
    assert len(trajs) == 1
    assert trajs[0].error is None
    assert trajs[0].infra_errored is False


def test_no_setup_cmd_runs_adapter():
    adapter = RecordingAdapter()
    trajs, _ = evaluate_task(
        _task(None), adapter, detectors=[], runs=1, sandbox_factory=FakeSandbox
    )
    assert adapter.calls == 1
    assert trajs[0].error is None
