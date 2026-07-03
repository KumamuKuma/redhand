from __future__ import annotations

import os

from redhand.demo import _iter_files


def test_iter_files_skips_bytecode_cache(tmp_path):
    solution = tmp_path / "solution"
    cache = solution / "__pycache__"
    cache.mkdir(parents=True)
    (solution / "money.py").write_text("ANSWER = 42\n", encoding="utf-8")
    (cache / "money.cpython-312.pyc").write_bytes(b"\xcb\r\r\n\x00\x00")

    rels = [os.path.relpath(path, solution) for path in _iter_files(str(solution))]

    assert rels == ["money.py"]
