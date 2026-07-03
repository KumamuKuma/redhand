"""Tests for the runner (scheduling, budget, pass^k) and the ClaudeCode
stream-json parser.

Everything here is offline: the runner is driven with MockAgentAdapter, and the
ClaudeCodeAdapter is exercised only through its pure ``consume_stream_json``
parser on canned JSONL — no subprocess, no network, no ``claude``.
"""

from __future__ import annotations

import json

from redhand.adapters import MockAgentAdapter, consume_stream_json
from redhand.contracts import Trajectory
from redhand.runner import (
    claimed_success_rate,
    estimate_pass_k,
    executed,
    is_budget_marker,
    pass_k_curve,
    run_task,
    total_cost,
    true_success_rate,
)

# Sibling test module (pytest prepends the tests dir to sys.path).
from _shcompat import TRUE, contains
from test_mock_adapter import FakeSandbox, make_task


def _factory():
    return FakeSandbox()


# --------------------------------------------------------------------------- #
# Scheduling
# --------------------------------------------------------------------------- #
def test_run_task_returns_one_trajectory_per_run():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "solution.txt", "content": "42\n"}],
        hidden_test_cmd=contains("42", "solution.txt"),
    )
    trajs = run_task(task, MockAgentAdapter(), _factory, runs=3)

    assert len(trajs) == 3
    assert [t.run_index for t in trajs] == [0, 1, 2]
    assert all(t.agent == "mock" for t in trajs)
    assert all(t.truly_succeeded for t in trajs)


def test_each_run_gets_a_fresh_sandbox():
    """A run that only exists because a *previous* run left state behind would
    fail here: each run starts from an empty workdir, so a task whose script
    writes the solution must pass every time, independently."""
    created = []

    def counting_factory():
        sb = FakeSandbox()
        created.append(sb.workdir)
        return sb

    task = make_task(
        mock_script=[{"tool": "Write", "path": "solution.txt", "content": "42"}],
        hidden_test_cmd=contains("42", "solution.txt"),
    )
    trajs = run_task(task, MockAgentAdapter(), counting_factory, runs=2)
    assert len(created) == 2
    assert created[0] != created[1]  # distinct sandboxes
    assert all(t.truly_succeeded for t in trajs)


# --------------------------------------------------------------------------- #
# pass^k and rates
# --------------------------------------------------------------------------- #
def test_pass_k_all_pass():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "s.txt", "content": "ok"}],
        hidden_test_cmd=contains("ok", "s.txt"),
    )
    trajs = run_task(task, MockAgentAdapter(), _factory, runs=4)

    assert true_success_rate(trajs) == 1.0
    assert estimate_pass_k(trajs, 1) == 1.0
    assert estimate_pass_k(trajs, 5) == 1.0
    assert pass_k_curve(trajs, [1, 2, 3]) == {1: 1.0, 2: 1.0, 3: 1.0}


def test_pass_k_never_pass():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "s.txt", "content": "wrong"}],
        visible_test_cmd=TRUE,
        hidden_test_cmd=contains("correct", "s.txt"),  # always fails
    )
    trajs = run_task(task, MockAgentAdapter(), _factory, runs=3)

    assert claimed_success_rate(trajs) == 1.0   # visible always passes
    assert true_success_rate(trajs) == 0.0      # hidden never passes
    assert estimate_pass_k(trajs, 1) == 0.0
    assert estimate_pass_k(trajs, 3) == 0.0


def test_pass_k_partial_is_p_to_the_k():
    """Half the runs truly pass -> pass^k == 0.5 ** k."""
    # Deterministically alternate pass/fail by using a hidden test that keys off
    # a per-run marker file the script writes. Simpler: two tasks won't do it, so
    # build trajectories directly with known hidden results.
    trajs = [
        Trajectory(task_id="t", agent="mock", run_index=i)
        for i in range(4)
    ]
    from redhand.contracts import TestResult

    passing = TestResult(passed=1, total=1, exit_code=0)
    failing = TestResult(passed=0, failed=1, total=1, exit_code=1)
    trajs[0].hidden_test_result = passing
    trajs[1].hidden_test_result = failing
    trajs[2].hidden_test_result = passing
    trajs[3].hidden_test_result = failing

    assert true_success_rate(trajs) == 0.5
    assert estimate_pass_k(trajs, 1) == 0.5
    assert estimate_pass_k(trajs, 2) == 0.25
    assert estimate_pass_k(trajs, 3) == 0.125


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
def test_budget_stops_and_marks():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "s.txt", "content": "ok"}],
        hidden_test_cmd=contains("ok", "s.txt"),
        metadata={"mock_cost_usd": 0.6},
    )
    trajs = run_task(
        task, MockAgentAdapter(), _factory, runs=5, max_total_cost_usd=1.0
    )

    # run0 (spent 0.6) + run1 (spent 1.2) execute; run2 is over budget -> marker.
    assert len(trajs) == 3
    assert not is_budget_marker(trajs[0])
    assert not is_budget_marker(trajs[1])
    assert is_budget_marker(trajs[2])
    assert trajs[2].error.startswith("budget_exceeded")

    ran = executed(trajs)
    assert len(ran) == 2
    assert total_cost(trajs) == 0.6 * 2  # marker adds no cost
    # rate math ignores the budget marker
    assert true_success_rate(trajs) == 1.0


def test_no_budget_runs_all():
    task = make_task(
        mock_script=[{"tool": "Write", "path": "s.txt", "content": "ok"}],
        hidden_test_cmd=contains("ok", "s.txt"),
        metadata={"mock_cost_usd": 5.0},
    )
    trajs = run_task(task, MockAgentAdapter(), _factory, runs=2)
    assert len(trajs) == 2
    assert not any(is_budget_marker(t) for t in trajs)


def test_runner_survives_adapter_crash():
    class Boom:
        name = "boom"

        def run(self, task, sandbox, run_index):
            raise RuntimeError("kaboom")

    task = make_task(mock_script=[])
    trajs = run_task(task, Boom(), _factory, runs=1)
    assert len(trajs) == 1
    assert trajs[0].error is not None
    assert "runner_error" in trajs[0].error
    assert "kaboom" in trajs[0].error


# --------------------------------------------------------------------------- #
# ClaudeCode stream-json parser (offline; canned JSONL)
# --------------------------------------------------------------------------- #
def _canned_stream_lines():
    """A minimal but faithful claude --output-format stream-json transcript:
    init -> assistant tool_use(Bash) -> tool_result -> assistant text -> result."""
    events = [
        {
            "type": "system",
            "subtype": "init",
            "session_id": "sess-123",
            "model": "claude-sonnet-5",
            "cwd": "/work",
            "tools": ["Bash", "Write"],
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Bash",
                        "input": {"command": "echo hi > note.txt && cat note.txt"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "tool_use_id": "toolu_1",
                        "type": "tool_result",
                        "content": "hi",
                        "is_error": False,
                    }
                ],
            },
            "tool_use_result": {"stdout": "hi", "stderr": "", "interrupted": False},
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "Done."}],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Done.",
            "session_id": "sess-123",
            "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 4267, "output_tokens": 42},
        },
    ]
    return [json.dumps(e) for e in events]


def test_stream_json_parser_builds_trajectory():
    sandbox = FakeSandbox()
    try:
        traj = Trajectory(task_id="t", agent="claude_code", run_index=0)
        traj.initial_snapshot_id = sandbox.snapshot("initial")

        result = consume_stream_json(_canned_stream_lines(), traj, sandbox)

        # terminal result surfaced
        assert result is not None
        assert result["subtype"] == "success"

        # steps: init note, tool_use(Bash), final text note
        tool_steps = [s for s in traj.steps if s.tool_call is not None]
        assert len(tool_steps) == 1
        bash_step = tool_steps[0]
        assert bash_step.tool_call.name == "Bash"
        assert bash_step.tool_call.arguments["command"].startswith("echo hi")
        assert bash_step.tool_call.raw is not None

        # tool_result attached as a CommandResult with stdout + snapshot
        assert bash_step.command is not None
        assert bash_step.command.stdout == "hi"
        assert bash_step.command.exit_code == 0
        assert bash_step.command.command.startswith("echo hi")
        assert bash_step.snapshot_id is not None

        # assistant text recorded as a note step
        assert any(s.note == "Done." for s in traj.steps)
        # init session note recorded
        assert any("session_id=sess-123" in s.note for s in traj.steps)
    finally:
        sandbox.teardown()


def test_stream_json_parser_is_robust_to_junk_lines():
    traj = Trajectory(task_id="t", agent="claude_code", run_index=0)
    lines = ["not json at all", "", "{bad", json.dumps({"type": "unknown"})]
    # Should not raise and should produce no steps / no result.
    result = consume_stream_json(lines, traj, sandbox=None)
    assert result is None
    assert traj.steps == []


def test_apply_result_maps_cost_and_tokens():
    from redhand.adapters.claude_code import ClaudeCodeAdapter

    traj = Trajectory(task_id="t", agent="claude_code", run_index=0)
    result = consume_stream_json(_canned_stream_lines(), traj, sandbox=None)
    ClaudeCodeAdapter._apply_result(result, traj)

    assert traj.cost_usd == 0.0123
    assert traj.tokens_in == 4267
    assert traj.tokens_out == 42
    assert traj.error is None


def test_claude_adapter_degrades_when_binary_missing():
    """Safe degradation: a bogus binary name -> error captured, no exception, and
    the trajectory is still shaped (tests attempted, snapshots taken)."""
    from redhand.adapters.claude_code import ClaudeCodeAdapter

    adapter = ClaudeCodeAdapter(binary="claude-does-not-exist-xyz")
    task = make_task(mock_script=[], visible_test_cmd=TRUE, hidden_test_cmd=TRUE)
    sandbox = FakeSandbox()
    try:
        sandbox.setup(task)
        traj = adapter.run(task, sandbox, run_index=0)
    finally:
        sandbox.teardown()

    assert traj.error is not None
    assert "not found" in traj.error
    assert traj.initial_snapshot_id is not None
    assert traj.final_snapshot_id is not None
    # tests still ran against the (empty) workdir
    assert traj.visible_test_result is not None
    assert traj.wallclock_s >= 0.0
