"""Cross-platform command construction (Windows paths exercised via monkeypatch).

The sandbox and adapters run on Linux/WSL/macOS and Windows. These tests pin the
platform-specific branches so the Windows behavior can't silently regress when
developed/CI'd on Linux.
"""

from __future__ import annotations

import os

import redhand.sandbox.local as local
from redhand.adapters.base import launch_prefix
from redhand.sandbox.local import LocalSandbox


def test_shell_argv_posix_uses_bash():
    sb = LocalSandbox()
    sb.network_mode = "degraded"
    assert sb._shell_argv("python -m pytest -q") == ["bash", "-c", "python -m pytest -q"]


def test_shell_argv_posix_namespace_wraps_unshare():
    sb = LocalSandbox()
    sb.network_mode = "namespace"
    assert sb._shell_argv("echo hi") == ["unshare", "-n", "bash", "-c", "echo hi"]


def test_run_command_windows_uses_shell_true_with_raw_string(monkeypatch, tmp_path):
    """On Windows, run_command must pass the raw command string via shell=True so
    cmd receives it verbatim (a list would let list2cmdline mangle quotes)."""
    captured = {}

    class _FakeProc:
        returncode = 0

        def communicate(self, timeout=None):
            return ("out", "err")

    def fake_popen(launch, **kwargs):
        captured["launch"] = launch
        captured["kwargs"] = kwargs
        return _FakeProc()

    monkeypatch.setattr(local, "_IS_WINDOWS", True)
    monkeypatch.setattr(local.subprocess, "Popen", fake_popen)
    sb = LocalSandbox()
    sb.workdir = str(tmp_path)      # satisfy _require_setup without a real setup
    sb._shadow_git = str(tmp_path)
    sb.run_command("python -m pytest -q")
    assert captured["launch"] == "python -m pytest -q"   # raw string, not a list
    assert captured["kwargs"].get("shell") is True


def test_launch_prefix_posix_resolves_path(monkeypatch):
    monkeypatch.setattr("redhand.adapters.base.shutil.which", lambda b: "/usr/local/bin/codex")
    monkeypatch.setattr(os, "name", "posix")
    assert launch_prefix("codex") == ["/usr/local/bin/codex"]


def test_launch_prefix_windows_wraps_cmd_shim(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("redhand.adapters.base.shutil.which", lambda b: r"C:\Users\me\AppData\npm\codex.cmd")
    pre = launch_prefix("codex")
    assert pre[0] == os.environ.get("ComSpec", "cmd.exe")
    assert pre[1] == "/c"
    assert pre[2] == r"C:\Users\me\AppData\npm\codex.cmd"


def test_launch_prefix_windows_exe_not_wrapped(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("redhand.adapters.base.shutil.which", lambda b: r"C:\tools\claude.exe")
    assert launch_prefix("claude") == [r"C:\tools\claude.exe"]
