"""Tests for CodexAdapter.

Everything here is offline: the ``codex`` CLI is never invoked with real work
(no network, no cost). ``_build_command`` is asserted against the probed
``codex exec`` flags, the ``--json`` event parser is exercised on canned JSONL,
and the missing-binary path is checked for safe degradation. The ``FakeSandbox``
and ``make_task`` helpers are reused from ``test_mock_adapter``.
"""

from __future__ import annotations

import json

from redhand.adapters import CodexAdapter, consume_codex_json
from redhand.adapters.base import launch_prefix
from redhand.adapters.codex import _CodexStreamConsumer  # noqa: F401 (import check)
from redhand.contracts import AgentAdapter, CommandResult, Trajectory

# Sibling test module (pytest prepends the tests dir to sys.path).
from test_mock_adapter import FakeSandbox, make_task


# --------------------------------------------------------------------------- #
# Command construction
# --------------------------------------------------------------------------- #
def test_codex_adapter_is_agent_adapter():
    assert isinstance(CodexAdapter(), AgentAdapter)
    assert CodexAdapter().name == "codex"


def test_build_command_default_argv():
    adapter = CodexAdapter()
    task = make_task()  # prompt == "do the thing"
    argv = adapter._build_command(task, "/work/dir")
    # argv starts with the cross-platform launch prefix (resolves "codex" on PATH,
    # wraps .cmd shims on Windows), then the probed exec flags.
    prefix = launch_prefix("codex")
    assert argv[: len(prefix)] == prefix
    assert argv[len(prefix):] == [
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--color",
        "never",
        "--ephemeral",
        "--cd",
        "/work/dir",
        "--",
        "do the thing",
    ]


def test_build_command_with_model_and_extra_args():
    adapter = CodexAdapter(
        model="gpt-5-codex", binary="/usr/local/bin/codex", extra_args=["--oss"]
    )
    task = make_task()
    argv = adapter._build_command(task, "/w")
    # binary is first, prompt is last after "--", model + extra args are threaded
    # in between (extra args before the "--" prompt guard).
    assert argv[0] == "/usr/local/bin/codex"
    assert argv[1] == "exec"
    assert "--model" in argv and argv[argv.index("--model") + 1] == "gpt-5-codex"
    assert "--oss" in argv
    assert argv[-2:] == ["--", "do the thing"]
    # model + extra args sit before the prompt separator
    assert argv.index("--oss") < argv.index("--")


# --------------------------------------------------------------------------- #
# JSON event parser (offline, canned events)
# --------------------------------------------------------------------------- #
def _canned_event_lines() -> list[str]:
    events = [
        {"type": "thread.started", "thread_id": "th-abc"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "echo hi > note.txt",
                "aggregated_output": "hi\n",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": "note.txt", "kind": "add"}],
            },
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "Done."},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 1234,
                "cached_input_tokens": 0,
                "output_tokens": 56,
            },
        },
    ]
    return [json.dumps(e) for e in events]


def test_codex_json_parser_builds_trajectory():
    sandbox = FakeSandbox()
    try:
        traj = Trajectory(task_id="t", agent="codex", run_index=0)
        traj.initial_snapshot_id = sandbox.snapshot("initial")

        summary = consume_codex_json(_canned_event_lines(), traj, sandbox)

        assert summary["completed"] is True
        assert summary["error"] is None
        assert summary["usage"]["input_tokens"] == 1234

        # thread note recorded
        assert any("thread_id=th-abc" in s.note for s in traj.steps)

        # command_execution -> a Bash tool call with a CommandResult + snapshot
        tool_steps = [s for s in traj.steps if s.tool_call is not None]
        names = [s.tool_call.name for s in tool_steps]
        assert "Bash" in names and "Edit" in names

        bash_step = next(s for s in tool_steps if s.tool_call.name == "Bash")
        assert isinstance(bash_step.command, CommandResult)
        assert bash_step.command.stdout == "hi\n"
        assert bash_step.command.exit_code == 0
        assert bash_step.command.command.startswith("echo hi")
        assert bash_step.snapshot_id is not None

        edit_step = next(s for s in tool_steps if s.tool_call.name == "Edit")
        assert "note.txt" in edit_step.note
        assert edit_step.snapshot_id is not None

        # assistant message recorded as a note
        assert any(s.note == "Done." for s in traj.steps)

        # usage maps onto tokens via _apply_usage
        consumer = _CodexStreamConsumer(traj, None)
        consumer.usage = summary["usage"]
        CodexAdapter._apply_usage(consumer, traj)
        assert traj.tokens_in == 1234
        assert traj.tokens_out == 56
        assert traj.cost_usd == 0.0
    finally:
        sandbox.teardown()


def test_codex_json_parser_is_robust_to_junk_lines():
    traj = Trajectory(task_id="t", agent="codex", run_index=0)
    lines = ["not json at all", "", "{bad", json.dumps({"type": "unknown"})]
    summary = consume_codex_json(lines, traj, sandbox=None)
    assert summary["completed"] is False
    assert summary["error"] is None
    assert traj.steps == []


def test_codex_json_parser_captures_turn_failed():
    traj = Trajectory(task_id="t", agent="codex", run_index=0)
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "th-1"}),
        json.dumps(
            {"type": "turn.failed", "error": {"message": "401 Unauthorized"}}
        ),
    ]
    summary = consume_codex_json(lines, traj, sandbox=None)
    assert summary["completed"] is False
    assert "401" in summary["error"]

    consumer = _CodexStreamConsumer(traj, None)
    consumer.error_msg = summary["error"]
    CodexAdapter._apply_usage(consumer, traj)
    assert traj.error is not None and "401" in traj.error


# --------------------------------------------------------------------------- #
# Safe degradation (no real codex invoked — a bogus binary name)
# --------------------------------------------------------------------------- #
def test_codex_adapter_degrades_when_binary_missing():
    """A bogus binary name -> error captured, no exception, and the trajectory is
    still shaped: snapshots taken and the (fake-sandbox) test runner invoked."""
    adapter = CodexAdapter(binary="codex-does-not-exist-xyz")
    task = make_task(mock_script=[])   # portable TRUE/TRUE test commands by default
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
    # visible + hidden tests still ran against the (empty) workdir
    assert traj.visible_test_result is not None
    assert traj.hidden_test_result is not None
    assert traj.wallclock_s >= 0.0
