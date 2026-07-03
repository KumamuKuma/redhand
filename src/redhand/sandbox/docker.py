"""redhand — DockerSandbox: a container-backed sandbox for real isolation.

``LocalSandbox`` runs the task's commands as restricted *host* subprocesses. That
is enough to catch a corner-cutting agent, but it is **not** a security boundary:
a determined agent with host filesystem access can search the disk for the
reference ``solution/`` or the held-out oracle. ``DockerSandbox`` closes that gap
for command/test execution by running each command inside a container that mounts
**only the working directory** (nothing else on the host is visible) with
``--network none`` (kernel-enforced, unlike the local backend's degraded mode).

It is a drop-in for :class:`redhand.sandbox.local.LocalSandbox` — same
:class:`redhand.contracts.Sandbox` Protocol — implemented as a subclass that
overrides only *how a command is launched* (:meth:`_launch_spec`). Snapshotting,
diffing, the held-out-oracle hardening, and teardown are inherited and run
host-side on the bind-mounted working copy, so all of that behaviour (and its
tests) is shared.

Scope & honesty
---------------
* This isolates ``run_command`` / ``run_tests`` / the oracle scoring. The **agent
  process itself** (the ``claude`` / ``codex`` CLI) is still launched on the host
  by the adapter, so for a fully adversarial setup you would additionally run the
  agent CLI inside the container — that is the documented next step, not shipped.
* Requires the ``docker`` CLI on ``PATH`` and a usable daemon. The default image
  has Python but **not** Node — pass ``image=`` a Node-capable image to score the
  JS/TS tasks.
* This backend has not been exercised against a live Docker daemon on the
  Docker-less development host; treat it as **beta**. The command construction and
  the no-Docker error path are unit-tested.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Optional

from redhand.sandbox.local import LocalSandbox

DEFAULT_BASE_DIR = os.environ.get(
    "REDHAND_SANDBOX_DIR", os.path.join(tempfile.gettempdir(), "redhand-sandboxes")
)

# Python-only by default. JS/TS tasks additionally need Node — pass an image such
# as ``nikolaik/python-nodejs:python3.12-nodejs20-slim`` for those.
DEFAULT_IMAGE = "python:3.12-slim"

_IS_WINDOWS = os.name == "nt"


def docker_available() -> bool:
    """True if the ``docker`` CLI is on ``PATH``. (Does not ping the daemon.)"""
    return shutil.which("docker") is not None


class DockerSandbox(LocalSandbox):
    """Container-backed sandbox: commands run inside a ``--network none`` container
    that mounts only the working copy. Same Protocol as ``LocalSandbox``."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        network: str = "none",
        base_dir: str = DEFAULT_BASE_DIR,
        max_output_bytes: Optional[int] = None,
    ) -> None:
        if max_output_bytes is None:
            super().__init__(base_dir=base_dir)
        else:
            super().__init__(base_dir=base_dir, max_output_bytes=max_output_bytes)
        self.image = image
        self.network = network

    def setup(self, task):  # type: ignore[override]
        if not docker_available():
            raise RuntimeError(
                "DockerSandbox requires the `docker` CLI on PATH (and a running "
                "daemon). Install Docker, or use redhand.sandbox.LocalSandbox."
            )
        workdir = super().setup(task)
        self.network_mode = "container"
        return workdir

    def _launch_spec(self, command: str, cwd: str) -> tuple:  # type: ignore[override]
        """Run ``command`` inside a throwaway container that sees only ``cwd``.

        ``docker run --rm --network <net> -v <cwd>:/work -w /work <image>
        sh -c <command>``. Because the same ``cwd`` (workdir for agent commands,
        the clean ``oracle/`` dir for held-out scoring) is the *only* mount, the
        host's task ``solution/`` and other tasks are simply not present in the
        container filesystem."""
        host = os.path.abspath(cwd)
        argv = [
            "docker", "run", "--rm",
            "--network", self.network,
            "-v", f"{host}:/work",
            "-w", "/work",
        ]
        if not _IS_WINDOWS:
            # keep files in the mounted dir owned by the host user (so host-side
            # git snapshot / teardown can read & remove them)
            argv += ["--user", f"{os.getuid()}:{os.getgid()}"]
        argv += [self.image, "sh", "-c", command]

        popen_kwargs: dict = dict(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if _IS_WINDOWS:
            popen_kwargs["creationflags"] = getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        else:
            popen_kwargs["start_new_session"] = True
        return argv, popen_kwargs
