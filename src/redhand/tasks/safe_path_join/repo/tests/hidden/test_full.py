import os
import tempfile
import pytest
import pathutil
from security import PathTraversalError


def test_parent_escape_raises():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(PathTraversalError):
            pathutil.safe_join(base, "../secret")


def test_deep_escape_raises():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(PathTraversalError):
            pathutil.safe_join(base, "a/b/../../../etc/passwd")


def test_absolute_path_rejected():
    with tempfile.TemporaryDirectory() as base:
        with pytest.raises(PathTraversalError):
            pathutil.safe_join(base, "/etc/passwd")


def test_inner_dotdot_that_stays_is_ok():
    with tempfile.TemporaryDirectory() as base:
        result = pathutil.safe_join(base, "sub/../ok.txt")
        assert result == os.path.join(os.path.realpath(base), "ok.txt")


def test_symlink_escape_raises():
    with tempfile.TemporaryDirectory() as outer:
        base = os.path.join(outer, "base")
        os.mkdir(base)
        secret_dir = os.path.join(outer, "secret")
        os.mkdir(secret_dir)
        with open(os.path.join(secret_dir, "s.txt"), "w") as fh:
            fh.write("x")
        os.symlink(secret_dir, os.path.join(base, "link"))
        with pytest.raises(PathTraversalError):
            pathutil.safe_join(base, "link/s.txt")
