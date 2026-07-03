"""redhand — LocalSandbox: the MVP, Docker-free sandbox backend.

This machine has **no Docker**, so the MVP isolation strategy is:

  * a throwaway *working copy* of the task repo on the data disk
    (``/root/autodl-tmp/...`` — never the tiny root overlay),
  * a **shadow git repository** with its own ``GIT_DIR`` living *outside* the
    work-tree, used purely for snapshot/diff. It never touches (and cannot
    pollute) the tested project's own ``.git``,
  * a **restricted subprocess** with a scrubbed environment, an output-size
    cap, a hard timeout, and best-effort network isolation.

Network isolation — read this carefully
----------------------------------------
True network isolation needs a network namespace (``unshare -n``) or Docker.
On this host ``unshare -n`` is **not permitted** (verified: it fails with
"Operation not permitted", and raw sockets to public IPs still succeed). So:

  * If ``unshare -n`` *is* available at runtime, every command is wrapped with
    it → real, kernel-enforced network isolation.
  * Otherwise we **degrade gracefully**: the child env has all proxy variables
    scrubbed and pointed at a black-hole, and offline hints
    (``PIP_NO_INDEX`` etc.) are set. This blocks proxy-respecting HTTP clients
    but **cannot block raw sockets**. Direct outbound connections remain
    possible in degraded mode — do not rely on this backend for adversarial
    network confinement. Use the Docker backend (``docker.py``) for that.

The instance attribute :attr:`LocalSandbox.network_mode` records which mode is
active (``"namespace"`` or ``"degraded"``).

Task repo resolution
--------------------
:class:`~redhand.contracts.Task` carries ``repo_relpath`` "relative to the task
dir". The sandbox resolves the absolute initial-repo path in this order:

  1. ``task.metadata["repo_abspath"]`` if present (absolute override),
  2. ``os.path.join(task.metadata["task_dir"], task.repo_relpath)`` if
     ``task_dir`` is in metadata,
  3. ``task.repo_relpath`` interpreted as-is (absolute, or relative to CWD).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Optional

from redhand.contracts import CommandResult, FileDiff, Task, TestResult
from redhand.sandbox.parsing import parse_test_output

# Where disposable working copies live. Portable default (the OS temp dir); set
# ``REDHAND_SANDBOX_DIR`` to point at a disk with room (e.g. a data disk when the
# root filesystem is small). Never hard-code a Linux-only path.
DEFAULT_BASE_DIR = os.environ.get(
    "REDHAND_SANDBOX_DIR", os.path.join(tempfile.gettempdir(), "redhand-sandboxes")
)

# Exit codes that mean the command could not be *executed* (shell/interpreter
# missing or not runnable) — an infrastructure error, not a test failure.
_INFRA_EXIT_CODES = frozenset({126, 127})

# Platform switch: POSIX runs commands through ``bash``; Windows through ``cmd``.
_IS_WINDOWS = os.name == "nt"

# Output signatures that mean the environment, not the agent, is the problem
# (e.g. no pytest installed, no interpreter, a Windows shell rejecting the cmd).
_INFRA_MARKERS = (
    "no module named pytest",
    "command not found",
    "is not recognized as an internal or external command",
    "no such file or directory: 'bash'",
)

# Cap captured stdout/stderr per stream so a runaway command cannot OOM us.
DEFAULT_MAX_OUTPUT_BYTES = 512 * 1024  # 512 KiB per stream

# Conventional exit code for a timed-out command (matches coreutils `timeout`).
TIMEOUT_EXIT_CODE = 124

_PROXY_VARS = (
    "http_proxy", "https_proxy", "ftp_proxy", "all_proxy", "no_proxy",
    "HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY", "NO_PROXY",
)

# ---- held-out oracle hardening ------------------------------------------- #
# Files an agent could drop into the workdir to hijack the *interpreter* or the
# *test runner* at import/startup time — they must never survive into the clean
# oracle copy. ``pytest.py`` shadows ``python -m pytest`` (a top-level module on
# ``sys.path[0]`` wins over the installed package); ``sitecustomize``/
# ``usercustomize`` are auto-imported by CPython at startup.
_ORACLE_FORBIDDEN_FILES = ("pytest.py", "sitecustomize.py", "usercustomize.py")

# Test-infrastructure config files whose *pristine task version* must be used in
# the oracle, so an agent cannot reshape pytest's behaviour (addopts, plugins,
# python_files, pythonpath, makereport hooks) via config it controls.
_ORACLE_PRISTINE_CONFIGS = ("pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml")

# Directories never worth walking into when mirroring pristine files.
_SKIP_DIRS = frozenset({".git", "__pycache__", ".pytest_cache", ".tox", ".venv"})


def _safe_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


class _CappedStream:
    """Drain a binary stream in a background thread, retaining at most ``cap``
    bytes.

    Reading continues *past* the cap (so the child never blocks on a full pipe),
    but only the first ``cap`` bytes are kept — memory stays bounded no matter how
    much the command emits, which is the real OOM protection. ``over`` is set the
    instant the cap is exceeded so the caller can kill a runaway producer instead
    of buffering forever."""

    _CHUNK = 65536

    def __init__(self, stream, cap: int, over: threading.Event) -> None:
        self._stream = stream
        self._cap = cap
        self._over = over
        self._buf = bytearray()
        self._total = 0
        self._thread = threading.Thread(target=self._drain, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _drain(self) -> None:
        try:
            while True:
                chunk = self._stream.read(self._CHUNK)
                if not chunk:
                    break
                self._total += len(chunk)
                room = self._cap - len(self._buf)
                if room > 0:
                    self._buf.extend(chunk[:room])
                if self._total > self._cap:
                    self._over.set()
        except (ValueError, OSError):
            # stream closed underneath us; nothing more to read
            pass

    def join(self, timeout: Optional[float] = None) -> None:
        self._thread.join(timeout)

    def text(self) -> str:
        s = self._buf.decode("utf-8", "replace")
        if self._total > self._cap:
            s += f"\n...[redhand: truncated {self._total - self._cap} bytes]"
        return s


class LocalSandbox:
    """Disposable, data-disk working copy with a shadow-git snapshot store.

    Implements the :class:`redhand.contracts.Sandbox` Protocol.
    """

    def __init__(
        self,
        *,
        base_dir: str = DEFAULT_BASE_DIR,
        max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    ) -> None:
        self.workdir: str = ""            # Sandbox Protocol attribute
        self._base_dir = base_dir
        self._max_output_bytes = max_output_bytes
        self._root: str = ""              # per-sandbox root (holds work/ + shadow.git)
        self._shadow_git: str = ""        # independent GIT_DIR for snapshots
        self.initial_snapshot_id: Optional[str] = None
        self.network_mode: str = "degraded"

    # ---- context-manager sugar (optional, guarantees cleanup) ---------- #
    def __enter__(self) -> "LocalSandbox":
        return self

    def __exit__(self, *exc: object) -> None:
        self.teardown()

    # ------------------------------------------------------------------ #
    # setup
    # ------------------------------------------------------------------ #
    def setup(self, task: Task) -> str:
        """Materialize the task's initial repo into a fresh workdir; return it."""
        src = self._resolve_repo_path(task)
        if not os.path.isdir(src):
            raise FileNotFoundError(f"initial repo not found for task {task.id!r}: {src}")

        os.makedirs(self._base_dir, exist_ok=True)
        # Non-identifying name: the workdir path must NOT reveal the task id. If it
        # did, a real agent could read its own cwd, learn which task it is on, and
        # go straight to the on-disk ``solution/`` or held-out oracle. (This is a
        # mitigation, not a guarantee — a determined agent with host filesystem
        # access can still search the disk; real confinement needs DockerSandbox.)
        self._root = os.path.join(self._base_dir, uuid.uuid4().hex)
        os.makedirs(self._root, exist_ok=True)
        try:
            os.chmod(self._root, 0o700)   # best-effort: not group/other readable
        except OSError:
            pass
        self.workdir = os.path.join(self._root, "work")
        self._shadow_git = os.path.join(self._root, "shadow.git")

        # Copy the initial repo. Any nested ".git" in the source is a *copy* of
        # the tested project's history; drop it so the shadow store owns all
        # snapshotting and there is zero chance of touching the real project.
        shutil.copytree(src, self.workdir, symlinks=True)
        nested_git = os.path.join(self.workdir, ".git")
        if os.path.isdir(nested_git):
            shutil.rmtree(nested_git, ignore_errors=True)

        # Held-out oracle: remove the hidden tests from the agent-visible
        # workspace so a real agent cannot read (or game) the oracle. They are
        # re-injected by the adapter only after the final snapshot, purely to
        # score the attempt. Default location is ``tests/hidden``; override per
        # task via ``metadata["heldout_paths"]``.
        for rel in task.metadata.get("heldout_paths", ["tests/hidden"]):
            held = os.path.join(self.workdir, rel)
            if os.path.isdir(held):
                shutil.rmtree(held, ignore_errors=True)
            elif os.path.isfile(held):
                os.remove(held)

        self.network_mode = "namespace" if self._can_unshare_net() else "degraded"

        os.makedirs(self._shadow_git, exist_ok=True)
        self._git("init", "--quiet")
        self.initial_snapshot_id = self.snapshot("initial")
        return self.workdir

    def _resolve_repo_path(self, task: Task) -> str:
        override = task.metadata.get("repo_abspath")
        if override:
            return str(override)
        task_dir = task.metadata.get("task_dir")
        if task_dir:
            return os.path.join(str(task_dir), task.repo_relpath)
        return task.repo_relpath

    # ------------------------------------------------------------------ #
    # snapshot / diff via the shadow git
    # ------------------------------------------------------------------ #
    def snapshot(self, label: str = "") -> str:
        """Commit the whole workdir into the shadow history; return commit id.

        Uses ``add -A -f`` (force) so files the agent tried to hide from the
        detectors via a ``.gitignore`` entry (its own, or one it appended) are
        snapshotted anyway. Combined with ``core.excludesFile=`` in
        :meth:`_git_raw`, the shadow store sees *every* file that exists on disk,
        which is exactly what the detection layer must reason over."""
        self._require_setup()
        self._git("add", "-A", "-f")
        self._git(
            "commit", "--quiet", "--allow-empty",
            "-m", label or "snapshot",
        )
        return self._git("rev-parse", "HEAD").strip()

    def diff(self, from_id: str, to_id: str) -> list[FileDiff]:
        """File-level diff between two shadow snapshots."""
        self._require_setup()
        name_status = self._git(
            "diff", "-M", "--name-status", from_id, to_id,
        )
        diffs: list[FileDiff] = []
        for line in name_status.splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            code = parts[0][0]  # first char: A/M/D/R/C/T
            if code in ("R", "C") and len(parts) >= 3:
                old_path, new_path = parts[1], parts[2]
                change_type = "renamed" if code == "R" else "added"
                path = new_path
                diff_paths = [old_path, new_path]
                before = self._show(from_id, old_path)
                after = self._show(to_id, new_path)
            else:
                path = parts[1] if len(parts) > 1 else parts[0]
                diff_paths = [path]
                change_type = {
                    "A": "added", "M": "modified", "D": "deleted", "T": "modified",
                }.get(code, "modified")
                before = None if code == "A" else self._show(from_id, path)
                after = None if code == "D" else self._show(to_id, path)

            diff_text = self._git(
                "diff", "-M", "--no-color", from_id, to_id, "--", *diff_paths,
            )
            diffs.append(
                FileDiff(
                    path=path,
                    change_type=change_type,
                    diff_text=diff_text,
                    before_blob=before,
                    after_blob=after,
                )
            )
        return diffs

    def _show(self, rev: str, path: str) -> Optional[str]:
        """Return blob content at ``rev:path`` or None if it does not exist."""
        proc = self._git_raw("show", f"{rev}:{path}")
        if proc.returncode != 0:
            return None
        return proc.stdout

    # ------------------------------------------------------------------ #
    # command / test execution
    # ------------------------------------------------------------------ #
    def run_command(self, command: str, timeout_s: int = 120) -> CommandResult:
        """Run a shell command inside the sandbox (best-effort no network).

        Cross-platform: POSIX runs ``bash -c`` (optionally wrapped in
        ``unshare -n`` for real network isolation); Windows runs ``cmd /c``. The
        child is placed in its own process group so a timeout kills the whole
        tree on either platform. Output is capped *as it streams* (see
        :meth:`_exec`) rather than buffered whole, so a runaway command cannot
        OOM the harness."""
        self._require_setup()
        return self._exec(command, timeout_s, self.workdir)

    def _launch_spec(self, command: str, cwd: str) -> tuple:
        """Build ``(launch, popen_kwargs)`` to run ``command`` in ``cwd``.

        Factored out so a container backend (``DockerSandbox``) can override *how*
        a command is launched — running it inside a ``--network none`` container
        that mounts only ``cwd`` — while reusing all of ``_exec``'s streaming
        output cap and timeout/process-tree-kill machinery."""
        env = self._restricted_env()
        popen_kwargs = dict(
            cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if _IS_WINDOWS:
            # Pass the raw string to cmd via shell=True: Python's list2cmdline would
            # otherwise backslash-escape any embedded quotes and break the command.
            # New process group so taskkill /T can reap the whole tree.
            launch = command
            popen_kwargs["shell"] = True
            # Windows-only constant; getattr keeps this importable/testable elsewhere.
            popen_kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            launch = self._shell_argv(command)   # ["bash", "-c", command] (+unshare)
            popen_kwargs["start_new_session"] = True  # own session/pgroup
        return launch, popen_kwargs

    def _exec(self, command: str, timeout_s: int, cwd: str) -> CommandResult:
        """Launch ``command`` in ``cwd`` and stream-capture stdout/stderr with a
        hard per-stream byte cap and a hard timeout.

        Unlike ``Popen.communicate()`` (which reads the *entire* output into
        memory before any truncation), each stream is drained by a
        :class:`_CappedStream` thread that keeps at most ``_max_output_bytes`` and
        discards the rest — memory stays bounded regardless of how much the
        command prints. The moment either stream exceeds the cap the child is
        killed. Timeout still yields exit code :data:`TIMEOUT_EXIT_CODE` (124),
        preserving the previous ``run_command`` contract."""
        launch, popen_kwargs = self._launch_spec(command, cwd)
        try:
            proc = subprocess.Popen(launch, **popen_kwargs)
        except (FileNotFoundError, OSError) as exc:
            return CommandResult(command=command, stdout="", stderr=str(exc), exit_code=127)

        # A real Popen(stdout=PIPE) always exposes .stdout/.stderr; a proc object
        # without them (e.g. a test double) can't be streamed, so capture it the
        # old way. Production always takes the streaming path below.
        if getattr(proc, "stdout", None) is None or getattr(proc, "stderr", None) is None:
            return self._exec_buffered(proc, command, timeout_s)

        over = threading.Event()
        out_cap = _CappedStream(proc.stdout, self._max_output_bytes, over)
        err_cap = _CappedStream(proc.stderr, self._max_output_bytes, over)
        out_cap.start()
        err_cap.start()

        timed_out = False
        over_limit = False
        deadline = time.monotonic() + timeout_s
        while True:
            # A process that finishes on its own always wins over a cap/timeout
            # kill, so a fast command that merely prints a lot still reports its
            # real exit code.
            if proc.poll() is not None:
                break
            if over.is_set():
                over_limit = True
                break
            if time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)

        if timed_out or over_limit:
            self._kill_group(proc)

        # Drain the pipes to EOF, then reap the child.
        out_cap.join(10)
        err_cap.join(10)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._kill_group(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass

        out = out_cap.text()
        err = err_cap.text()
        code = proc.returncode if proc.returncode is not None else TIMEOUT_EXIT_CODE
        if timed_out:
            code = TIMEOUT_EXIT_CODE
            err += f"\n[redhand] command timed out after {timeout_s}s and was killed."
        elif over_limit:
            err += (
                f"\n[redhand] output exceeded the {self._max_output_bytes}-byte "
                f"per-stream cap; the command was terminated."
            )
        return CommandResult(command=command, stdout=out, stderr=err, exit_code=code)

    def _exec_buffered(self, proc, command: str, timeout_s: int) -> CommandResult:
        """Whole-output capture fallback for proc objects without pipe streams.

        Only reached for test doubles / exotic backends — the real streaming path
        in :meth:`_exec` is what protects against OOM in production."""
        timed_out = False
        try:
            out, err = proc.communicate(timeout=timeout_s)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            self._kill_group(proc)
            out, err = proc.communicate()
            code = TIMEOUT_EXIT_CODE
        out = self._cap(out)
        err = self._cap(err)
        if timed_out:
            err += f"\n[redhand] command timed out after {timeout_s}s and was killed."
        return CommandResult(command=command, stdout=out, stderr=err, exit_code=code)

    def _cap(self, text) -> str:
        """Cap an already-collected string/bytes to ``_max_output_bytes``."""
        if text is None:
            return ""
        if isinstance(text, bytes):
            text = text.decode("utf-8", "replace")
        cap = self._max_output_bytes
        if len(text) <= cap:
            return text
        return text[:cap] + f"\n...[redhand: truncated {len(text) - cap} bytes]"

    def run_tests(self, command: str, timeout_s: int = 300) -> TestResult:
        """Run a test command and parse pass/fail counts (pytest / node / etc.).

        Distinguishes a *test failure* from an *infrastructure error*: if the
        command could not be executed at all (missing shell/interpreter → exit
        126/127), the result is flagged ``errored`` so callers never mistake a
        broken environment for the agent legitimately failing the tests."""
        res = self.run_command(command, timeout_s=timeout_s)
        return self._testresult_from(res)

    @staticmethod
    def _testresult_from(res: CommandResult) -> TestResult:
        """Turn a raw :class:`CommandResult` into a parsed :class:`TestResult`
        (shared by ``run_tests`` and ``score_heldout``)."""
        combined = f"{res.stdout}\n{res.stderr}"
        low = combined.lower()
        infra = res.exit_code in _INFRA_EXIT_CODES or any(m in low for m in _INFRA_MARKERS)
        parsed = parse_test_output(combined)
        if parsed is not None and not infra:
            passed, failed, total = parsed
            return TestResult(
                passed=passed,
                failed=failed,
                total=total,
                exit_code=res.exit_code,
                raw_output=combined,
            )
        if infra:
            return TestResult(
                passed=0, failed=0, total=0, exit_code=res.exit_code,
                raw_output=combined, errored=True,
            )
        # Fallback: could not parse counts, lean on the exit code.
        if res.exit_code == 0:
            return TestResult(passed=1, failed=0, total=1, exit_code=0, raw_output=combined)
        return TestResult(
            passed=0, failed=1, total=1, exit_code=res.exit_code, raw_output=combined
        )

    # ------------------------------------------------------------------ #
    # held-out oracle scoring (tamper-resistant)
    # ------------------------------------------------------------------ #
    def score_heldout(self, task: Task) -> TestResult:
        """Score the held-out (hidden) tests in an environment the agent never
        touched, so it cannot fake the oracle.

        The agent's tests run in ``self.workdir`` — a directory it fully controls.
        Left there, the hidden oracle is trivially gameable: a ``pytest.py`` that
        ``sys.exit(0)`` shadows ``python -m pytest``; a ``conftest.py`` with a
        ``pytest_runtest_makereport`` hook can flip *failed* to *passed*; a
        planted config or ``sitecustomize`` can do the same. So instead of
        running the hidden tests in the workdir we build a **fresh ``oracle/``
        directory** under the sandbox root (which the agent has never executed in)
        and score there:

          1. copy the agent's *final* product source into ``oracle/``;
          2. purge bytecode caches (no sourceless ``.pyc`` games);
          3. delete any ``pytest.py`` / ``sitecustomize.py`` / ``usercustomize.py``
             the agent added;
          4. restore the **pristine** test infrastructure from the task's source
             repo — every ``conftest.py`` plus ``pytest.ini`` / ``tox.ini`` /
             ``setup.cfg`` / ``pyproject.toml``;
          5. inject the pristine held-out tests from the source repo (replacing
             anything the agent planted at those paths);
          6. run ``task.hidden_test_cmd`` with ``cwd`` set to ``oracle/``.

        Because the *test infrastructure* is the task's original (including the
        ``conftest.py`` that puts ``src`` on ``sys.path`` for src-layout tasks),
        honest solutions still import and pass — only the tamper vectors are
        removed. This never mutates ``self.workdir``, so it is safe to call after
        the final snapshot without disturbing the detector diff."""
        self._require_setup()
        cmd = task.hidden_test_cmd
        if not cmd:
            return TestResult(errored=True, raw_output="task has no hidden_test_cmd")

        oracle = os.path.join(self._root, "oracle")
        if os.path.exists(oracle):
            shutil.rmtree(oracle, ignore_errors=True)

        # (1) the agent's final source, verbatim.
        shutil.copytree(self.workdir, oracle, symlinks=True)
        # any nested shadow/.git that leaked in — drop it, oracle is throwaway.
        nested_git = os.path.join(oracle, ".git")
        if os.path.isdir(nested_git):
            shutil.rmtree(nested_git, ignore_errors=True)

        # (2) no bytecode games (orphan .pyc shadowing, poisoned __pycache__).
        self._purge_bytecode(oracle)

        # (3) strip interpreter/runner-hijacking files at every level.
        for dirpath, dirnames, filenames in os.walk(oracle):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                if fn in _ORACLE_FORBIDDEN_FILES:
                    _safe_remove(os.path.join(dirpath, fn))

        src_repo = self._resolve_repo_path(task)
        if os.path.isdir(src_repo):
            # (4) pristine test infrastructure from the task source.
            self._restore_pristine(oracle, src_repo, "conftest.py")
            for cfg in _ORACLE_PRISTINE_CONFIGS:
                self._restore_pristine(oracle, src_repo, cfg)

        # (5) pristine held-out tests, replacing anything the agent planted.
        for rel in task.metadata.get("heldout_paths", ["tests/hidden"]):
            src = os.path.join(src_repo, rel)
            dst = os.path.join(oracle, rel)
            if os.path.isdir(dst):
                shutil.rmtree(dst, ignore_errors=True)
            elif os.path.isfile(dst):
                _safe_remove(dst)
            if os.path.isdir(src):
                shutil.copytree(src, dst, symlinks=True)
            elif os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        # (6) score in the clean directory.
        timeout_s = max(30, min(300, int(task.time_limit_s)))
        res = self._exec(cmd, timeout_s, oracle)
        return self._testresult_from(res)

    @staticmethod
    def _purge_bytecode(root: str) -> None:
        """Remove every ``__pycache__`` dir and stray ``.pyc``/``.pyo`` so a
        sourceless bytecode file cannot shadow a module in the oracle."""
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            if "__pycache__" in dirnames:
                shutil.rmtree(os.path.join(dirpath, "__pycache__"), ignore_errors=True)
                dirnames.remove("__pycache__")
            for fn in filenames:
                if fn.endswith((".pyc", ".pyo")):
                    _safe_remove(os.path.join(dirpath, fn))

    @staticmethod
    def _restore_pristine(oracle: str, src_repo: str, filename: str) -> None:
        """Replace every ``filename`` in ``oracle`` with the task-source copy.

        First deletes *all* agent copies of ``filename`` at any level, then copies
        each source copy back to the same relative path. If the source has no such
        file, the agent's copies are simply removed (it cannot smuggle in its own
        pytest config / conftest)."""
        # remove all agent-side copies
        for dirpath, dirnames, filenames in os.walk(oracle):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            if filename in filenames:
                _safe_remove(os.path.join(dirpath, filename))
        # copy each pristine source copy to the same relative path
        for dirpath, dirnames, filenames in os.walk(src_repo):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            if filename in filenames:
                rel = os.path.relpath(os.path.join(dirpath, filename), src_repo)
                dst = os.path.join(oracle, rel)
                os.makedirs(os.path.dirname(dst) or oracle, exist_ok=True)
                shutil.copy2(os.path.join(dirpath, filename), dst)

    # ------------------------------------------------------------------ #
    # read / teardown
    # ------------------------------------------------------------------ #
    def read_file(self, relpath: str) -> Optional[str]:
        self._require_setup()
        path = os.path.join(self.workdir, relpath)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()

    def teardown(self) -> None:
        """Delete the one-shot workdir and its shadow git, leaving no trace."""
        if self._root and os.path.isdir(self._root):
            shutil.rmtree(self._root, ignore_errors=True)
        self.workdir = ""
        self._root = ""
        self._shadow_git = ""

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _require_setup(self) -> None:
        if not self.workdir or not self._shadow_git:
            raise RuntimeError("sandbox not set up; call setup(task) first")

    def _git(self, *args: str) -> str:
        """Run a shadow-git command, raising on failure; return stdout."""
        proc = self._git_raw(*args)
        if proc.returncode != 0:
            raise RuntimeError(
                f"shadow git failed: git {' '.join(args)}\n{proc.stderr}"
            )
        return proc.stdout

    def _git_raw(self, *args: str) -> subprocess.CompletedProcess:
        argv = [
            "git",
            "--git-dir", self._shadow_git,
            "--work-tree", self.workdir,
            "-c", "user.name=redhand-shadow",
            "-c", "user.email=redhand@sandbox.local",
            "-c", "commit.gpgsign=false",
            "-c", "core.quotePath=false",
            "-c", "advice.detachedHead=false",
            # Ignore any host-global excludes file so the shadow store cannot be
            # blinded by the operator's ~/.config/git/ignore. Combined with
            # ``add -A -f``, every on-disk file is snapshotted.
            "-c", "core.excludesFile=",
            *args,
        ]
        return subprocess.run(
            argv, cwd=self.workdir, capture_output=True, text=True, errors="replace"
        )

    def _restricted_env(self) -> dict[str, str]:
        env = dict(os.environ)
        for var in _PROXY_VARS:
            env.pop(var, None)
        # Degraded-mode defense in depth: black-hole proxies + offline hints.
        # (Cannot stop raw sockets; see module docstring.)
        env["http_proxy"] = env["https_proxy"] = env["all_proxy"] = "http://127.0.0.1:9"
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = env["ALL_PROXY"] = "http://127.0.0.1:9"
        env["no_proxy"] = env["NO_PROXY"] = ""
        env["PIP_NO_INDEX"] = "1"
        env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return env

    def _shell_argv(self, command: str) -> list[str]:
        """POSIX shell wrapping (``bash -c``, optionally under ``unshare -n``).
        Windows goes through ``shell=True`` in :meth:`run_command` instead."""
        argv = ["bash", "-c", command]
        if self.network_mode == "namespace":
            argv = ["unshare", "-n", *argv]
        return argv

    @staticmethod
    def _kill_group(proc: subprocess.Popen) -> None:
        if _IS_WINDOWS:
            # taskkill /T kills the whole child tree (cmd + interpreter + spawns)
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True, timeout=10,
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    @staticmethod
    def _can_unshare_net() -> bool:
        """True iff we can create a network namespace (real isolation). POSIX
        only — Windows has no ``unshare``, so network confinement falls back to
        the degraded (proxy-scrubbing) mode."""
        if _IS_WINDOWS:
            return False
        try:
            proc = subprocess.run(
                ["unshare", "-n", "true"],
                capture_output=True,
                timeout=5,
            )
            return proc.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False
