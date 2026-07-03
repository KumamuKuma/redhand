import os
import tempfile
import pathutil


def test_joins_within_base():
    with tempfile.TemporaryDirectory() as base:
        result = pathutil.safe_join(base, "docs/readme.txt")
        assert result == os.path.join(os.path.realpath(base), "docs", "readme.txt")


def test_plain_file():
    with tempfile.TemporaryDirectory() as base:
        result = pathutil.safe_join(base, "a.txt")
        assert result.endswith("a.txt")
