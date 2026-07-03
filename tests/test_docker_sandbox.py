"""DockerSandbox: offline construction + graceful no-Docker behaviour.

The container backend can't be exercised against a live daemon on the Docker-less
CI/dev host, so we test the parts that don't need Docker: the command it *would*
run (``docker run --network none`` mounting only the cwd), and that it fails with
a clear message when Docker is absent.
"""

from __future__ import annotations

import os

import pytest

from redhand.sandbox import DockerSandbox, LocalSandbox, docker_available
from redhand.sandbox.docker import DEFAULT_IMAGE


def test_is_a_localsandbox_subclass():
    # drop-in: same Protocol, inherits snapshot/diff/oracle/teardown
    assert issubclass(DockerSandbox, LocalSandbox)


def test_docker_available_returns_bool():
    assert isinstance(docker_available(), bool)


def test_launch_spec_builds_isolated_container_command():
    sb = DockerSandbox(image="img:tag", network="none")
    argv, kwargs = sb._launch_spec("python -m pytest tests/hidden -q", "/some/where")
    # a throwaway container, no network, mounting ONLY the given cwd at /work
    assert argv[:5] == ["docker", "run", "--rm", "--network", "none"]
    assert "-v" in argv and f"{os.path.abspath('/some/where')}:/work" in argv
    assert argv[argv.index("-w") + 1] == "/work"
    assert "img:tag" in argv
    # the command is handed to a shell inside the container, verbatim
    assert argv[-3:] == ["sh", "-c", "python -m pytest tests/hidden -q"]
    assert kwargs["stdout"] is not None and kwargs["stderr"] is not None


def test_launch_spec_mounts_the_given_cwd_not_a_fixed_workdir():
    # the oracle scoring runs with cwd=<oracle dir>; the container must mount THAT,
    # not the agent workdir, or the held-out oracle would run against the wrong tree
    sb = DockerSandbox()
    argv_a, _ = sb._launch_spec("echo hi", "/tmp/a/work")
    argv_b, _ = sb._launch_spec("echo hi", "/tmp/a/oracle")
    assert f"{os.path.abspath('/tmp/a/work')}:/work" in argv_a
    assert f"{os.path.abspath('/tmp/a/oracle')}:/work" in argv_b


def test_default_image_documented_python_only():
    assert DockerSandbox().image == DEFAULT_IMAGE


def test_setup_raises_clearly_without_docker(monkeypatch, tmp_path):
    # simulate no docker on PATH -> a clear, actionable error (not a cryptic crash)
    monkeypatch.setattr("redhand.sandbox.docker.shutil.which", lambda _b: None)
    from redhand.contracts import Task

    repo = tmp_path / "repo"
    (repo / "tests" / "visible").mkdir(parents=True)
    task = Task(
        id="t", name="t", language="python", difficulty="easy", prompt="x",
        repo_relpath="repo", visible_test_cmd="", hidden_test_cmd="",
        honest_solution_note="", metadata={"repo_abspath": str(repo)},
    )
    with pytest.raises(RuntimeError, match="requires the `docker` CLI"):
        DockerSandbox().setup(task)
