"""redhand evaluation loop — the orchestration that wires every module together.

For each (task, adapter, run) it:

1. builds a fresh :class:`~redhand.sandbox.local.LocalSandbox`,
2. lets the adapter drive the agent and produce a :class:`Trajectory`,
3. runs the detector layer **while the sandbox is still alive** (detectors need
   ``sandbox.diff`` / ``sandbox.read_file``),
4. tears the sandbox down,

enforcing a cost budget and never letting one crash abort the batch. Returns the
flat ``(trajectories, detection_results)`` the scoring/reporting layer consumes.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional, Sequence

from redhand.contracts import (
    AgentAdapter,
    DetectionResult,
    Detector,
    Sandbox,
    Task,
    TestResult,
    Trajectory,
)
from redhand.detectors import DEFAULT_DETECTORS, run_detectors
from redhand.sandbox.local import LocalSandbox

SandboxFactory = Callable[[], Sandbox]
_BUDGET_MARKER = "budget_exceeded"


def _default_sandbox_factory() -> Sandbox:
    return LocalSandbox()


def evaluate_task(
    task: Task,
    adapter: AgentAdapter,
    *,
    detectors: Optional[Sequence[Detector]] = None,
    runs: int = 1,
    max_total_cost_usd: Optional[float] = None,
    sandbox_factory: SandboxFactory = _default_sandbox_factory,
) -> tuple[list[Trajectory], list[DetectionResult]]:
    """Run one (agent, task) pair ``runs`` times with detection each run."""
    dets = list(detectors) if detectors is not None else DEFAULT_DETECTORS
    agent_name = getattr(adapter, "name", "unknown")
    trajectories: list[Trajectory] = []
    detections: list[DetectionResult] = []
    spent = 0.0

    for run_index in range(runs):
        if max_total_cost_usd is not None and spent >= max_total_cost_usd:
            trajectories.append(
                Trajectory(
                    task_id=task.id, agent=agent_name, run_index=run_index,
                    error=f"{_BUDGET_MARKER}: spent ${spent:.4f} >= "
                          f"budget ${max_total_cost_usd:.4f}",
                )
            )
            break

        traj, det = _run_once(task, adapter, dets, run_index, agent_name, sandbox_factory)
        trajectories.append(traj)
        detections.append(det)
        spent += traj.cost_usd or 0.0

    return trajectories, detections


def _run_once(task, adapter, dets, run_index, agent_name, sandbox_factory):
    sandbox: Optional[Sandbox] = None
    try:
        sandbox = sandbox_factory()
        sandbox.setup(task)
        # optional per-task environment prep (deps, build) before the agent acts.
        # If it fails, the environment is broken — flag the run as an infra error
        # and skip the (wasted, unfair) agent invocation rather than proceeding.
        if task.setup_cmd:
            setup = sandbox.run_command(task.setup_cmd, timeout_s=max(60, task.time_limit_s))
            if setup.exit_code != 0:
                detail = (setup.stderr or setup.stdout or "")[:300]
                traj = Trajectory(
                    task_id=task.id, agent=agent_name, run_index=run_index,
                    error=f"setup_cmd failed (exit {setup.exit_code}): {detail}",
                    visible_test_result=TestResult(
                        errored=True, exit_code=setup.exit_code,
                        raw_output=(setup.stdout + setup.stderr),
                    ),
                )
                return traj, DetectionResult(
                    task_id=task.id, agent=agent_name, run_index=run_index
                )
        traj = adapter.run(task, sandbox, run_index)
        det = run_detectors(task, traj, sandbox, dets)   # sandbox still alive
        return traj, det
    except Exception as exc:  # adapter/sandbox/detector crash — isolate it
        traj = Trajectory(
            task_id=task.id, agent=agent_name, run_index=run_index,
            error=f"eval_error: {type(exc).__name__}: {exc}",
        )
        return traj, DetectionResult(task_id=task.id, agent=agent_name, run_index=run_index)
    finally:
        if sandbox is not None:
            try:
                sandbox.teardown()
            except Exception:
                pass


def evaluate(
    tasks: Iterable[Task],
    adapters: Iterable[AgentAdapter],
    *,
    detectors: Optional[Sequence[Detector]] = None,
    runs: int = 1,
    max_total_cost_usd: Optional[float] = None,
    sandbox_factory: SandboxFactory = _default_sandbox_factory,
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> tuple[list[Trajectory], list[DetectionResult]]:
    """Run every adapter over every task; return flat (trajectories, detections)."""
    tasks = list(tasks)
    adapters = list(adapters)
    all_traj: list[Trajectory] = []
    all_det: list[DetectionResult] = []
    for task in tasks:
        for adapter in adapters:
            if on_progress:
                on_progress(getattr(adapter, "name", "?"), task.id)
            trajs, dets = evaluate_task(
                task, adapter, detectors=detectors, runs=runs,
                max_total_cost_usd=max_total_cost_usd, sandbox_factory=sandbox_factory,
            )
            all_traj.extend(trajs)
            all_det.extend(dets)
    return all_traj, all_det
