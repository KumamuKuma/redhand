"""CodexAdapter — drives the real OpenAI ``codex`` CLI headless over one task.

MVP target: the ``codex exec`` subcommand (Codex's non-interactive mode) with
``--json`` so it prints one JSON event per line (JSONL), run with
``cwd = sandbox.workdir`` (and ``--cd <workdir>``) so the agent edits the task's
working copy directly. We parse the event stream into ``ToolCall`` /
``CommandResult`` objects, snapshot the sandbox after each file-mutating event,
run the visible + hidden tests, and record token usage — all onto a
``redhand.contracts.Trajectory``.

Key assumptions about the ``codex`` headless interface (verified against
codex-cli 0.139.0 with ``codex --help`` / ``codex exec --help`` and one live
smoke run; see module tests for canned samples):

* ``codex exec "<prompt>" --json`` runs non-interactively and prints one JSON
  object per line to stdout. The prompt is a positional argument (Codex also
  reads it from stdin if omitted; we always pass it explicitly and close stdin).
* Non-interactive control flags (all are ``codex exec`` flags):
    - ``--skip-git-repo-check`` — allow running outside a Git repository.
    - ``-s/--sandbox workspace-write`` — let the agent write to the workspace
      without per-command approval. ``codex exec`` never raises interactive
      approval prompts, so no ``--ask-for-approval`` is needed (and it is not an
      ``exec`` flag). The redhand sandbox is the real isolation boundary.
    - ``--ephemeral`` — do not persist session files to disk (leave no state).
    - ``--color never`` — no ANSI escapes in the stream.
    - ``-C/--cd <DIR>`` — working root for the agent.
    - ``-m/--model <MODEL>`` — model selection (optional).
* Events carry a top-level ``"type"`` (the thread/turn/item schema):
    - ``thread.started`` — ``{"thread_id": ...}`` (recorded as a note).
    - ``turn.started`` / ``item.started`` / ``item.updated`` — ignored (we act
      only on completed items to avoid double-counting).
    - ``item.completed`` — ``{"item": {...}}``. We care about:
        * ``command_execution`` — ``command`` + ``aggregated_output`` +
          ``exit_code`` -> a ``Bash`` ToolCall with an attached CommandResult.
        * ``file_change`` — ``changes: [{"path","kind"}]`` -> an ``Edit`` ToolCall.
        * ``agent_message`` — assistant text, recorded as a note step.
    - ``turn.completed`` — ``{"usage": {"input_tokens","output_tokens", ...}}``.
    - ``turn.failed`` / ``error`` — carry an error ``message``.

Codex on a ChatGPT subscription reports token usage but no per-run USD cost, so
``cost_usd`` is left at 0.0 (tokens are still recorded).

Safe degradation: if ``codex`` is missing, the process errors, or the run times
out, we never raise out of ``run`` — the failure is written to
``Trajectory.error`` and we still snapshot + run whatever tests we can. Because
detection relies on file diffs (captured by the snapshots), the adapter still
produces a useful trajectory even when event parsing is minimal.
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

# item.completed "item" types that mutate the workspace (we snapshot after them).
_COMMAND_ITEM_TYPES = {"command_execution", "local_shell_call", "exec_command"}
_FILE_CHANGE_ITEM_TYPES = {"file_change", "patch_apply", "apply_patch"}
_MESSAGE_ITEM_TYPES = {"agent_message", "assistant_message"}

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


class _CodexStreamConsumer:
    """Stateful parser: feed it one JSONL line at a time.

    Mutates ``trajectory`` in place (appending steps, attaching command results,
    snapshotting after each file-mutating item) and accumulates the terminal
    usage / error signals on ``self.usage`` / ``self.error_msg`` /
    ``self.completed``.
    """

    def __init__(self, trajectory: Trajectory, sandbox: Optional[Sandbox]):
        self.trajectory = trajectory
        self.sandbox = sandbox
        self._prev_snapshot = trajectory.initial_snapshot_id
        self._logical_step = 0
        self.usage: dict[str, Any] = {}
        self.error_msg: Optional[str] = None
        self.completed = False

    def feed(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            return  # ignore non-JSON noise (codex logs some lines to stderr)
        if not isinstance(event, dict):
            return
        etype = event.get("type")
        if etype == "thread.started":
            self._on_thread_started(event)
        elif etype == "item.completed":
            self._on_item(event.get("item") or {})
        elif etype == "turn.completed":
            self._on_turn_completed(event)
        elif etype == "turn.failed":
            self._on_turn_failed(event)
        elif etype == "error":
            msg = event.get("message")
            if msg:
                self.error_msg = str(msg)
        # turn.started / item.started / item.updated and unknown types: ignore.

    # -- handlers ----------------------------------------------------------
    def _on_thread_started(self, event: dict[str, Any]) -> None:
        tid = event.get("thread_id")
        if tid:
            self.trajectory.steps.append(
                TrajectoryStep(
                    index=len(self.trajectory.steps), note=f"thread_id={tid}"
                )
            )

    def _on_item(self, item: dict[str, Any]) -> None:
        if not isinstance(item, dict):
            return
        itype = str(item.get("type") or item.get("item_type") or "")
        if itype in _COMMAND_ITEM_TYPES:
            self._on_command(item)
        elif itype in _FILE_CHANGE_ITEM_TYPES:
            self._on_file_change(item)
        elif itype in _MESSAGE_ITEM_TYPES:
            text = str(item.get("text") or item.get("message") or "").strip()
            if text:
                self.trajectory.steps.append(
                    TrajectoryStep(index=len(self.trajectory.steps), note=text)
                )
        # reasoning / todo_list / web_search / mcp_tool_call: ignored (no diff).

    def _on_command(self, item: dict[str, Any]) -> None:
        self._logical_step += 1
        command = item.get("command")
        if isinstance(command, list):
            command = " ".join(str(c) for c in command)
        command = str(command or "")
        tool_call = ToolCall(
            step=self._logical_step,
            name="Bash",
            arguments={"command": command},
            raw=json.dumps(item, ensure_ascii=False),
        )
        step = TrajectoryStep(index=len(self.trajectory.steps), tool_call=tool_call)
        output = item.get("aggregated_output")
        if output is None:
            output = item.get("output") or item.get("stdout") or ""
        exit_code = item.get("exit_code")
        if exit_code is None:
            status = item.get("status")
            exit_code = 1 if status in ("failed", "error") else 0
        try:
            ec = int(exit_code)
        except (TypeError, ValueError):
            ec = 0
        step.command = CommandResult(
            command=command, stdout=str(output), stderr="", exit_code=ec
        )
        self.trajectory.steps.append(step)
        self._snapshot_step(step)

    def _on_file_change(self, item: dict[str, Any]) -> None:
        self._logical_step += 1
        changes = item.get("changes")
        if changes is None:
            changes = item.get("files") or []
        paths: list[str] = []
        if isinstance(changes, list):
            for ch in changes:
                if isinstance(ch, dict) and ch.get("path"):
                    paths.append(str(ch.get("path")))
        tool_call = ToolCall(
            step=self._logical_step,
            name="Edit",
            arguments={"changes": changes},
            raw=json.dumps(item, ensure_ascii=False),
        )
        step = TrajectoryStep(
            index=len(self.trajectory.steps),
            tool_call=tool_call,
            note="file_change: " + ", ".join(paths) if paths else "file_change",
        )
        self.trajectory.steps.append(step)
        self._snapshot_step(step)

    def _on_turn_completed(self, event: dict[str, Any]) -> None:
        self.completed = True
        usage = event.get("usage")
        if isinstance(usage, dict):
            self.usage = usage

    def _on_turn_failed(self, event: dict[str, Any]) -> None:
        err = event.get("error")
        if isinstance(err, dict):
            self.error_msg = str(err.get("message") or err)
        elif err:
            self.error_msg = str(err)
        else:
            self.error_msg = "turn.failed"

    def _snapshot_step(self, step: TrajectoryStep) -> None:
        if self.sandbox is None:
            return
        snap = safe_snapshot(self.sandbox, f"step{step.index}")
        if snap:
            step.snapshot_id = snap
            step.file_diffs = safe_diff(self.sandbox, self._prev_snapshot, snap)
            self._prev_snapshot = snap


def consume_codex_json(
    lines: list[str], trajectory: Trajectory, sandbox: Optional[Sandbox] = None
) -> dict[str, Any]:
    """Parse a list of codex ``--json`` lines into ``trajectory``; return a summary
    ``{"usage", "error", "completed"}``. Pure/offline — used by tests to validate
    the parser without ever invoking ``codex``."""
    consumer = _CodexStreamConsumer(trajectory, sandbox)
    for line in lines:
        consumer.feed(line)
    return {
        "usage": consumer.usage,
        "error": consumer.error_msg,
        "completed": consumer.completed,
    }


class CodexAdapter(AdapterBase):
    """Drives the real ``codex`` CLI headless over one task."""

    name = "codex"

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        max_cost_usd: Optional[float] = None,
        binary: str = "codex",
        extra_args: Optional[list[str]] = None,
    ):
        self.model = model
        # Kept for interface parity with other adapters; codex exec has no budget
        # flag, so this is advisory only.
        self.max_cost_usd = max_cost_usd
        self.binary = binary
        self.extra_args = list(extra_args or [])

    # ------------------------------------------------------------------ #
    def run(self, task: Task, sandbox: Sandbox, run_index: int) -> Trajectory:
        traj = Trajectory(task_id=task.id, agent=self.name, run_index=run_index)
        t0 = time.monotonic()
        traj.initial_snapshot_id = self._snapshot(sandbox, "initial")
        consumer = _CodexStreamConsumer(traj, sandbox)

        command = self._build_command(task, sandbox.workdir)
        proc: Optional[subprocess.Popen] = None
        timed_out = {"value": False}
        try:
            proc = subprocess.Popen(
                command,
                cwd=sandbox.workdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                **_new_process_group_kwargs(),
            )
        except FileNotFoundError as exc:
            traj.error = f"codex CLI not found ({self.binary}): {exc}"
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
            elif consumer.error_msg and not consumer.completed:
                traj.error = traj.error or f"codex_error: {consumer.error_msg[:500]}"
            elif not consumer.completed and returncode not in (0, None):
                traj.error = (
                    traj.error or f"codex exited {returncode}: {stderr_text[:500]}"
                )

        self._apply_usage(consumer, traj)

        traj.final_snapshot_id = self._snapshot(sandbox, "final")
        self._run_visible_and_hidden(task, sandbox, traj)
        traj.wallclock_s = time.monotonic() - t0
        return traj

    # ------------------------------------------------------------------ #
    def _build_command(self, task: Task, workdir: str) -> list[str]:
        cmd = [
            *launch_prefix(self.binary),
            "exec",
            "--json",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--ephemeral",
            "--cd",
            workdir,
        ]
        if self.model:
            cmd += ["--model", self.model]
        cmd += self.extra_args
        # ``--`` guards against prompts that begin with ``-`` or look like a
        # subcommand (exec has resume/review/help subcommands).
        cmd += ["--", task.prompt]
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
    def _apply_usage(consumer: "_CodexStreamConsumer", traj: Trajectory) -> None:
        usage = consumer.usage or {}
        try:
            traj.tokens_in = int(
                usage.get("input_tokens") or usage.get("prompt_tokens") or 0
            )
        except (TypeError, ValueError):
            traj.tokens_in = 0
        try:
            traj.tokens_out = int(
                usage.get("output_tokens") or usage.get("completion_tokens") or 0
            )
        except (TypeError, ValueError):
            traj.tokens_out = 0
        # codex (ChatGPT subscription) reports no per-run USD cost; leave 0.0.
        if consumer.error_msg and not consumer.completed and not traj.error:
            traj.error = f"codex_error: {consumer.error_msg[:500]}"
