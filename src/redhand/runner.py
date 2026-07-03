"""redhand runner — schedule repeated (agent, task) attempts and aggregate them.

The runner owns the *harness loop*: for each of ``runs`` attempts it materializes
a fresh sandbox, hands it to the adapter, collects the ``Trajectory``, tears the
sandbox down, and enforces a cost budget. It deliberately stays thin — the
adapter drives the agent and fills in test results; the runner just orchestrates
and does the pass^k / rate math the reporting layer builds on.

pass^k
------
We define ``pass^k`` as *the estimated probability that k independent runs all
truly pass the hidden (held-out) tests* — i.e. ``p ** k`` where ``p`` is the
empirical fraction of executed runs whose ``hidden_test_result.all_passed`` is
true. (This is the "reliability under repetition" reading, the complement of
``pass@k``.)
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from redhand.contracts import AgentAdapter, Sandbox, Task, Trajectory

SandboxFactory = Callable[[], Sandbox]

_BUDGET_MARKER = "budget_exceeded"


def run_task(
    task: Task,
    adapter: AgentAdapter,
    sandbox_factory: SandboxFactory,
    runs: int = 1,
    *,
    max_total_cost_usd: Optional[float] = None,
) -> list[Trajectory]:
    """Run ``task`` with ``adapter`` ``runs`` times, one fresh sandbox per run.

    Returns one ``Trajectory`` per attempt. If ``max_total_cost_usd`` is set and
    the accumulated ``cost_usd`` reaches it, scheduling stops early and a final
    marker trajectory (``error`` starting with ``"budget_exceeded"``) is appended
    so callers can see the budget cap was hit.
    """
    trajectories: list[Trajectory] = []
    spent = 0.0
    agent_name = getattr(adapter, "name", "unknown")

    for run_index in range(runs):
        if max_total_cost_usd is not None and spent >= max_total_cost_usd:
            trajectories.append(
                Trajectory(
                    task_id=task.id,
                    agent=agent_name,
                    run_index=run_index,
                    error=(
                        f"{_BUDGET_MARKER}: spent ${spent:.4f} >= "
                        f"budget ${max_total_cost_usd:.4f}"
                    ),
                )
            )
            break

        traj = _run_once(task, adapter, sandbox_factory, run_index, agent_name)
        trajectories.append(traj)
        spent += traj.cost_usd or 0.0

    return trajectories


def _run_once(
    task: Task,
    adapter: AgentAdapter,
    sandbox_factory: SandboxFactory,
    run_index: int,
    agent_name: str,
) -> Trajectory:
    sandbox: Optional[Sandbox] = None
    try:
        sandbox = sandbox_factory()
        sandbox.setup(task)
        return adapter.run(task, sandbox, run_index)
    except Exception as exc:  # adapter/sandbox crash — never abort the whole suite
        return Trajectory(
            task_id=task.id,
            agent=agent_name,
            run_index=run_index,
            error=f"runner_error: {type(exc).__name__}: {exc}",
        )
    finally:
        if sandbox is not None:
            try:
                sandbox.teardown()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Aggregation helpers (the pieces reporting builds TaskScore from).
# --------------------------------------------------------------------------- #
def is_budget_marker(traj: Trajectory) -> bool:
    return bool(traj.error) and traj.error.startswith(_BUDGET_MARKER)


def executed(trajectories: Iterable[Trajectory]) -> list[Trajectory]:
    """The runs that actually attempted the task (excludes budget markers)."""
    return [t for t in trajectories if not is_budget_marker(t)]


def true_success_rate(trajectories: Iterable[Trajectory]) -> float:
    """Fraction of executed runs whose hidden tests all passed."""
    runs = executed(trajectories)
    if not runs:
        return 0.0
    return sum(1 for t in runs if t.truly_succeeded) / len(runs)


def claimed_success_rate(trajectories: Iterable[Trajectory]) -> float:
    """Fraction of executed runs whose visible tests all passed."""
    runs = executed(trajectories)
    if not runs:
        return 0.0
    return sum(1 for t in runs if t.claimed_success) / len(runs)


def estimate_pass_k(trajectories: Iterable[Trajectory], k: int) -> float:
    """Estimated P(all k independent runs truly pass) = p ** k."""
    if k <= 0:
        return 1.0
    return true_success_rate(trajectories) ** k


def pass_k_curve(
    trajectories: Iterable[Trajectory], ks: Iterable[int]
) -> dict[int, float]:
    runs = list(trajectories)
    return {k: estimate_pass_k(runs, k) for k in ks}


def total_cost(trajectories: Iterable[Trajectory]) -> float:
    return sum(t.cost_usd or 0.0 for t in trajectories)
