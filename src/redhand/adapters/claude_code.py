"""ClaudeCodeAdapter — drives a real Claude Code agent headless over one task.

MVP target: the ``claude`` CLI in *print* mode (``claude -p``) with
``--output-format stream-json``, run with ``cwd = sandbox.workdir`` so the
agent edits the task's working copy directly. We parse the newline-delimited
JSON (JSONL) event stream into ``ToolCall`` / ``CommandResult`` objects, snapshot
the sandbox after each tool result, run the visible + hidden tests, and record
tokens / cost / wallclock — all onto a ``redhand.contracts.Trajectory``.

Key assumptions about the ``claude`` headless interface (verified against CLI
2.1.198 with small experiments; see module tests for canned samples):

* ``claude -p "<prompt>" --output-format stream-json --verbose`` prints one JSON
  object per line. ``--verbose`` is *required* for stream-json.
* Event objects carry a top-level ``"type"``:
    - ``system`` (``subtype == "init"``): session metadata (session_id, tools,
      model, cwd). We record the session id as a note.
    - ``assistant``: ``message.content`` is a list of blocks. We care about
      ``tool_use`` blocks — ``{"type":"tool_use","id","name","input":{...}}`` —
      which become ToolCalls (``name`` = tool name, ``input`` = arguments) — and
      ``text`` blocks, recorded as note steps.
    - ``user``: tool results. ``message.content`` holds
      ``{"type":"tool_result","tool_use_id","content","is_error"}`` and the event
      also has a top-level ``tool_use_result`` with ``stdout`` / ``stderr`` for
      Bash. We attach a CommandResult to the matching tool step.
    - ``result`` (``subtype == "success"``): terminal summary with
      ``total_cost_usd``, ``usage.input_tokens`` / ``usage.output_tokens``,
      ``is_error``, ``result`` (final text), ``session_id``.
* ``--permission-mode bypassPermissions`` runs tools without interactive
  approval (the sandbox is the isolation boundary). We also disable session
  persistence to avoid leaving state behind.

Safe degradation: if ``claude`` is missing, the process errors, or the run times
out, we never raise out of ``run`` — the failure is written to
``Trajectory.error`` and we still snapshot + run whatever tests we can.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from typing import Any, Optional

from redhand.adapters.base import AdapterBase, launch_prefix, safe_diff, safe_snapshot
from redhand.contracts import (
    CommandResult,
    Sandbox,
    Task,
    ToolCall,
    Trajectory,
    TrajectoryStep,
)

# Tool names whose result stdout/stderr map onto a CommandResult.
_SHELL_TOOLS = {"Bash", "BashOutput"}

_IS_WINDOWS = os.name == "nt"
# signal.SIGKILL is POSIX-only; fall back where it is absent (e.g. Windows).
_SIGKILL = getattr(signal, "SIGKILL", getattr(signal, "SIGTERM", 15))


def _new_process_group_kwargs() -> dict[str, Any]:
    """Popen kwargs that isolate the agent in its own process group / session.

    Without this the agent's tool subprocesses (bash, python, node, MCP servers)
    share our group, so a timeout kill reaches only the direct child and leaves
    orphans running that race the scoring/cleanup that follows. POSIX opens a new
    session (``start_new_session``); Windows a new process group.
    """
    if _IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill the agent process *and its whole subtree*, best-effort.

    POSIX signals the process group (``killpg``); Windows uses ``taskkill /T``.
    Any failure falls back to killing just the direct child so a broken platform
    never leaves ``run`` hanging or the watchdog raising.
    """
    try:
        if _IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
            )
        else:
            os.killpg(os.getpgid(proc.pid), _SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


class _StreamConsumer:
    """Stateful parser: feed it one JSONL line at a time.

    Mutates ``trajectory`` in place (appending steps, attaching command results,
    snapshotting after each tool result) and captures the terminal ``result``
    event on ``self.result_obj``.
    """

    def __init__(self, trajectory: Trajectory, sandbox: Optional[Sandbox]):
        self.trajectory = trajectory
        self.sandbox = sandbox
        self._prev_snapshot = trajectory.initial_snapshot_id
        self._tool_step_by_id: dict[str, TrajectoryStep] = {}
        self._logical_step = 0
        self.result_obj: Optional[dict[str, Any]] = None

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            return  # ignore non-JSON noise defensively
        if not isinstance(event, dict):
            return
        etype = event.get("type")
        if etype == "system":
            self._on_system(event)
        elif etype == "assistant":
            self._on_assistant(event)
        elif etype == "user":
            self._on_user(event)
        elif etype == "result":
            self.result_obj = event

    # -- handlers ----------------------------------------------------------
    def _on_system(self, event: dict[str, Any]) -> None:
        if event.get("subtype") == "init":
            sid = event.get("session_id")
            if sid:
                self.trajectory.steps.append(
                    TrajectoryStep(
                        index=len(self.trajectory.steps),
                        note=f"session_id={sid} model={event.get('model', '')}",
                    )
                )

    def _on_assistant(self, event: dict[str, Any]) -> None:
        message = event.get("message") or {}
        for block in message.get("content") or []:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_use":
                self._logical_step += 1
                tool_call = ToolCall(
                    step=self._logical_step,
                    name=str(block.get("name", "")),
                    arguments=block.get("input") or {},
                    raw=json.dumps(block, ensure_ascii=False),
                )
                step = TrajectoryStep(
                    index=len(self.trajectory.steps), tool_call=tool_call
                )
                self.trajectory.steps.append(step)
                tool_id = block.get("id")
                if tool_id:
                    self._tool_step_by_id[tool_id] = step
            elif btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    self.trajectory.steps.append(
                        TrajectoryStep(index=len(self.trajectory.steps), note=text)
                    )

    def _on_user(self, event: dict[str, Any]) -> None:
        message = event.get("message") or {}
        content = message.get("content")
        tool_use_result = event.get("tool_use_result")
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tool_id = block.get("tool_use_id")
            step = self._tool_step_by_id.get(tool_id)
            if step is None:
                continue
            is_error = bool(block.get("is_error"))
            stdout = ""
            stderr = ""
            if isinstance(tool_use_result, dict):
                stdout = tool_use_result.get("stdout") or ""
                stderr = tool_use_result.get("stderr") or ""
            if not stdout and not stderr:
                # Fall back to the textual tool_result content.
                raw = block.get("content")
                if isinstance(raw, str):
                    stdout = raw
                elif isinstance(raw, list):
                    stdout = "".join(
                        b.get("text", "")
                        for b in raw
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
            command = ""
            if step.tool_call and step.tool_call.name in _SHELL_TOOLS:
                command = str(step.tool_call.arguments.get("command", ""))
            step.command = CommandResult(
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=1 if is_error else 0,
            )
            self._snapshot_step(step)

    def _snapshot_step(self, step: TrajectoryStep) -> None:
        if self.sandbox is None:
            return
        snap = safe_snapshot(self.sandbox, f"step{step.index}")
        if snap:
            step.snapshot_id = snap
            step.file_diffs = safe_diff(self.sandbox, self._prev_snapshot, snap)
            self._prev_snapshot = snap


def consume_stream_json(
    lines: list[str], trajectory: Trajectory, sandbox: Optional[Sandbox] = None
) -> Optional[dict[str, Any]]:
    """Parse a list of stream-json lines into ``trajectory``; return the terminal
    ``result`` event dict (or None). Pure/offline — used by tests to validate the
    parser without ever invoking ``claude``."""
    consumer = _StreamConsumer(trajectory, sandbox)
    for line in lines:
        consumer.feed(line)
    return consumer.result_obj


class ClaudeCodeAdapter(AdapterBase):
    """Drives the real ``claude`` CLI headless over one task."""

    name = "claude_code"

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        allowed_tools: Optional[str] = None,
        max_cost_usd: Optional[float] = None,
        binary: str = "claude",
        extra_args: Optional[list[str]] = None,
    ):
        self.model = model
        self.allowed_tools = allowed_tools
        self.max_cost_usd = max_cost_usd
        self.binary = binary
        self.extra_args = list(extra_args or [])

    # ------------------------------------------------------------------ #
    def run(self, task: Task, sandbox: Sandbox, run_index: int) -> Trajectory:
        traj = Trajectory(task_id=task.id, agent=self.name, run_index=run_index)
        t0 = time.monotonic()
        traj.initial_snapshot_id = self._snapshot(sandbox, "initial")
        consumer = _StreamConsumer(traj, sandbox)

        command = self._build_command(task)
        proc: Optional[subprocess.Popen] = None
        timed_out = {"value": False}
        try:
            proc = subprocess.Popen(
                command,
                cwd=sandbox.workdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                **_new_process_group_kwargs(),
            )
        except FileNotFoundError as exc:
            traj.error = f"claude CLI not found ({self.binary}): {exc}"
        except Exception as exc:  # pragma: no cover - defensive
            traj.error = f"launch_error: {type(exc).__name__}: {exc}"

        if proc is not None:
            watchdog = threading.Timer(
                max(1, int(task.time_limit_s)), self._kill, args=(proc, timed_out)
            )
            watchdog.start()
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    consumer.feed(line)
            except Exception as exc:  # pragma: no cover - defensive
                traj.error = (traj.error or "") + f" stream_error: {exc}"
            finally:
                watchdog.cancel()

            stderr_text = self._drain_stderr(proc)
            returncode = self._reap(proc)

            if timed_out["value"]:
                traj.error = f"timeout after {task.time_limit_s}s"
            elif consumer.result_obj is None and returncode not in (0, None):
                traj.error = (
                    traj.error
                    or f"claude exited {returncode}: {stderr_text[:500]}"
                )

        self._apply_result(consumer.result_obj, traj)

        traj.final_snapshot_id = self._snapshot(sandbox, "final")
        self._run_visible_and_hidden(task, sandbox, traj)
        traj.wallclock_s = time.monotonic() - t0
        return traj

    # ------------------------------------------------------------------ #
    def _build_command(self, task: Task) -> list[str]:
        cmd = [
            *launch_prefix(self.binary),
            "-p",
            task.prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "bypassPermissions",
            "--no-session-persistence",
        ]
        if self.model:
            cmd += ["--model", self.model]
        if self.allowed_tools:
            cmd += ["--allowedTools", self.allowed_tools]
        if self.max_cost_usd is not None:
            cmd += ["--max-budget-usd", str(self.max_cost_usd)]
        cmd += self.extra_args
        return cmd

    @staticmethod
    def _kill(proc: subprocess.Popen, flag: dict[str, bool]) -> None:
        flag["value"] = True
        _kill_process_tree(proc)

    @staticmethod
    def _drain_stderr(proc: subprocess.Popen) -> str:
        try:
            if proc.stderr is not None:
                return proc.stderr.read() or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _reap(proc: subprocess.Popen) -> Optional[int]:
        try:
            proc.wait(timeout=10)
        except Exception:
            _kill_process_tree(proc)
        return proc.returncode

    @staticmethod
    def _apply_result(result: Optional[dict[str, Any]], traj: Trajectory) -> None:
        if not result:
            return
        try:
            traj.cost_usd = float(result.get("total_cost_usd") or 0.0)
        except (TypeError, ValueError):
            traj.cost_usd = 0.0
        usage = result.get("usage") or {}
        traj.tokens_in = int(usage.get("input_tokens") or 0)
        traj.tokens_out = int(usage.get("output_tokens") or 0)
        subtype = result.get("subtype")
        if result.get("is_error") or (subtype not in (None, "success")):
            traj.error = traj.error or f"claude_result_error: subtype={subtype}"
