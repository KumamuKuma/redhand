"""redhand.sandbox — isolated, disposable execution environments for one task.

Backends implement the :class:`redhand.contracts.Sandbox` Protocol:

  * :class:`~redhand.sandbox.local.LocalSandbox` — the MVP: a throwaway
    working copy on the data disk + a shadow git for snapshot/diff + a
    restricted, best-effort-networkless subprocess. Works without Docker.
  * :class:`~redhand.sandbox.docker.DockerSandbox` — container backend (beta):
    commands run inside a ``--network none`` container that mounts only the
    workdir, giving real, kernel-enforced isolation for command/test execution.
"""

from redhand.sandbox.docker import DockerSandbox, docker_available
from redhand.sandbox.local import LocalSandbox
from redhand.sandbox.parsing import parse_test_output

__all__ = ["LocalSandbox", "DockerSandbox", "docker_available", "parse_test_output"]
