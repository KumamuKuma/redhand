"""MockAgentAdapter — a deterministic, offline stand-in for a real coding agent.

It never calls an LLM, never touches the network, and costs nothing. Instead it
replays a fixed *script* of tool actions declared on the task, so the whole
pipeline (sandbox → runner → detectors → reporting) can be exercised in tests
with fully predictable trajectories.

Script contract
---------------
The script lives at ``Task.metadata["mock_script"]`` and is a list of action
dicts. Each action names a ``tool`` and its arguments — mirroring the real tool
names Claude Code emits, so detectors written against real trajectories also see
mock ones:

    {"tool": "Write", "path": <relpath>, "content": <str>}
        Create/overwrite ``<relpath>`` (relative to ``sandbox.workdir``) with
        ``content``. Parent directories are created.

    {"tool": "Edit",  "path": <relpath>, "old": <str>, "new": <str>}
        Read the file, replace every occurrence of ``old`` with ``new``, write
        it back.

    {"tool": "Bash",  "command": <str>}
        Run ``command`` via ``sandbox.run_command`` and record the
        ``CommandResult`` on the step.

    {"tool": "Read",  "path": <relpath>}
        Read a file (recorded as a Read tool call; content is not stored on the
        step, matching how a real agent's Read is a no-op on the workdir).

Any other ``tool`` value is recorded verbatim as a ToolCall with the whole
action dict as ``arguments`` (useful for exercising unknown-tool handling).

Optional deterministic knobs (also under ``Task.metadata``):

    "mock_cost_usd":   float  -> Trajectory.cost_usd for this run   (default 0.0)
    "mock_tokens_in":  int    -> Trajectory.tokens_in               (default 0)
    "mock_tokens_out": int    -> Trajectory.tokens_out              (default 0)
    "mock_error":      str    -> set Trajectory.error (simulate a crash/timeout)

After every action the adapter snapshots the sandbox and records the file diff
against the previous snapshot, then runs the visible and hidden test commands to
fill in the trajectory's test results — exactly as a real adapter must.
"""

from __future__ import annotations

import os
import time
from typing import Any

from redhand.adapters.base import AdapterBase
from redhand.contracts import (
    CommandResult,
    Sandbox,
    Task,
    ToolCall,
    Trajectory,
    TrajectoryStep,
)


class MockAgentAdapter(AdapterBase):
    """Replays ``Task.metadata['mock_script']`` against a sandbox."""

    name = "mock"

    def run(self, task: Task, sandbox: Sandbox, run_index: int) -> Trajectory:
        traj = Trajectory(task_id=task.id, agent=self.name, run_index=run_index)
        t0 = time.monotonic()
        metadata: dict[str, Any] = task.metadata or {}

        traj.initial_snapshot_id = self._snapshot(sandbox, "initial")
        prev_snapshot = traj.initial_snapshot_id

        script = metadata.get("mock_script") or []
        for step_no, action in enumerate(script, start=1):
            tool_call, command_result = self._execute(sandbox, step_no, action)
            step = TrajectoryStep(
                index=len(traj.steps),
                tool_call=tool_call,
                command=command_result,
            )
            snap = self._snapshot(sandbox, f"step{step.index}")
            if snap:
                step.snapshot_id = snap
                step.file_diffs = self._diff(sandbox, prev_snapshot, snap)
                prev_snapshot = snap
            traj.steps.append(step)

        traj.cost_usd = float(metadata.get("mock_cost_usd", 0.0) or 0.0)
        traj.tokens_in = int(metadata.get("mock_tokens_in", 0) or 0)
        traj.tokens_out = int(metadata.get("mock_tokens_out", 0) or 0)
        if metadata.get("mock_error"):
            traj.error = str(metadata["mock_error"])

        traj.final_snapshot_id = self._snapshot(sandbox, "final")
        self._run_visible_and_hidden(task, sandbox, traj)
        traj.wallclock_s = time.monotonic() - t0
        return traj

    # ------------------------------------------------------------------ #
    # action execution
    # ------------------------------------------------------------------ #
    def _execute(
        self, sandbox: Sandbox, step_no: int, action: dict[str, Any]
    ) -> tuple[ToolCall, CommandResult | None]:
        tool = action.get("tool")

        if tool == "Write":
            path = action["path"]
            content = action.get("content", "")
            self._write_file(sandbox, path, content)
            return ToolCall(step=step_no, name="Write",
                            arguments={"path": path, "content": content}), None

        if tool == "Edit":
            path = action["path"]
            old = action.get("old", "")
            new = action.get("new", "")
            current = sandbox.read_file(path) or ""
            self._write_file(sandbox, path, current.replace(old, new))
            return ToolCall(step=step_no, name="Edit",
                            arguments={"path": path, "old": old, "new": new}), None

        if tool == "Read":
            path = action["path"]
            sandbox.read_file(path)  # exercise the read; content not stored
            return ToolCall(step=step_no, name="Read", arguments={"path": path}), None

        if tool == "Bash":
            command = action["command"]
            result = sandbox.run_command(command)
            return ToolCall(step=step_no, name="Bash",
                            arguments={"command": command}), result

        # Unknown tool: record it verbatim so tests can assert on it.
        return ToolCall(step=step_no, name=str(tool), arguments=dict(action)), None

    def _write_file(self, sandbox: Sandbox, relpath: str, content: str) -> None:
        full = os.path.join(sandbox.workdir, relpath)
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(content)
