"""Internal AST + diff utilities for the detector layer.

This module is **private to ``redhand.detectors``**. It wraps two things the
deterministic detectors lean on:

* tree-sitter parsing (via ``tree-sitter-language-pack``) behind a tiny, stable
  helper surface (``kind`` / ``text`` / ``line`` / ``children`` / ``find`` …)
  that is agnostic to whether the installed binding exposes node accessors as
  properties or as methods; and
* unified-diff parsing plus "net diff" reconstruction, so a detector can ask for
  the effective before/after of every file the agent touched regardless of
  whether it is handed a live ``Sandbox`` or only a recorded ``Trajectory``.

Nothing here decides whether something is *sabotage* — that lives in the
detectors. Keeping the mechanical parsing here keeps each detector short and
lets them all agree on the same notion of "what changed".
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable, Iterator, Optional

from redhand.contracts import FileDiff, Trajectory

# --------------------------------------------------------------------------- #
# Language / file classification
# --------------------------------------------------------------------------- #
_PY_EXT = {".py", ".pyi"}
_JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}

_CONFIG_FILENAMES = {
    "setup.cfg", "tox.ini", "pyproject.toml", "mypy.ini", ".mypy.ini",
    ".flake8", "flake8.ini", ".pylintrc", "pylintrc", ".bandit", "bandit.yaml",
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json", ".eslintrc.yml",
    ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs",
    "tsconfig.json", "jsconfig.json", ".pre-commit-config.yaml",
    "ruff.toml", ".ruff.toml", "Makefile", "makefile", "GNUmakefile",
    "package.json", ".editorconfig", "pytest.ini", "conftest.py",
}
_CI_DIR_MARKERS = (".github/workflows/", ".gitlab-ci", ".circleci/", ".travis")


def language_for_path(path: str) -> Optional[str]:
    """Return the tree-sitter language name for a path, or None if unsupported.

    TypeScript is parsed with the JavaScript grammar as a fallback: the subset we
    care about (``it``/``describe``/``expect``/plain functions) parses fine, and
    files that fail to parse are simply skipped (fail-closed = no false positive).
    """
    _, ext = os.path.splitext(path.lower())
    if ext in _PY_EXT:
        return "python"
    if ext in _JS_EXT:
        return "javascript"
    return None


def is_test_file(path: str) -> bool:
    """Heuristic: does this path look like a test file? Conservative on purpose."""
    p = path.replace("\\", "/").lower()
    base = os.path.basename(p)
    if base in ("conftest.py",):
        return True
    # Python conventions
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py") or base.endswith("_tests.py"):
        return True
    # JS/TS conventions
    for suf in (".test.js", ".test.jsx", ".test.ts", ".test.tsx",
                ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx"):
        if base.endswith(suf):
            return True
    # Directory conventions
    parts = p.split("/")
    if "__tests__" in parts:
        return True
    for i, seg in enumerate(parts[:-1]):
        if seg in ("test", "tests", "spec", "specs"):
            return True
    return False


def is_config_file(path: str) -> bool:
    p = path.replace("\\", "/")
    base = os.path.basename(p)
    if base in _CONFIG_FILENAMES:
        return True
    if any(marker in p for marker in _CI_DIR_MARKERS):
        return True
    if base.endswith((".yml", ".yaml")) and ("ci" in base or "workflow" in p):
        return True
    if base.endswith(".sh") or base.endswith(".mk"):
        return True
    return False


# --------------------------------------------------------------------------- #
# tree-sitter wrapper — binding-agnostic node access
# --------------------------------------------------------------------------- #
def _call(x: Any) -> Any:
    """Return ``x()`` if it is a zero-arg accessor method, else ``x``.

    The installed binding exposes ``node.kind``/``node.start_byte``/… as methods;
    the reference py-tree-sitter binding exposes them as properties. This keeps us
    working on either without a hard dependency on the binding flavour.
    """
    return x() if callable(x) else x


@lru_cache(maxsize=8)
def _get_parser(language: str):
    from tree_sitter_language_pack import get_parser  # lazy: import cost off hot path

    return get_parser(language)  # type: ignore[arg-type]


@dataclass
class ParsedSource:
    """A parsed source buffer: the tree-sitter root node plus the raw bytes.

    Detectors always go through the ``kind``/``text``/``line`` helpers rather than
    poking at ``root`` directly, so the binding quirks stay contained here.
    """

    root: Any
    data: bytes
    language: str

    @property
    def ok(self) -> bool:
        return self.root is not None


def parse_source(source: Optional[str], language: str) -> ParsedSource:
    """Parse ``source`` in ``language``; never raises — returns ``ok=False`` instead.

    Fail-closed is deliberate: a parse failure must translate to "detector saw
    nothing", never to a spurious detection.
    """
    if source is None:
        return ParsedSource(None, b"", language)
    try:
        parser = _get_parser(language)
        tree = parser.parse(source)
        root = _call(tree.root_node)
        return ParsedSource(root, source.encode("utf-8", "replace"), language)
    except Exception:
        return ParsedSource(None, b"", language)


def kind(node: Any) -> str:
    return _call(node.kind) if hasattr(node, "kind") else _call(node.type)


def start_byte(node: Any) -> int:
    return _call(node.start_byte)


def end_byte(node: Any) -> int:
    return _call(node.end_byte)


def text(node: Any, parsed: ParsedSource) -> str:
    return parsed.data[start_byte(node):end_byte(node)].decode("utf-8", "replace")


def line(node: Any) -> int:
    """1-indexed start line of ``node``."""
    try:
        pt = _call(node.start_position)
        return int(pt.row) + 1
    except Exception:
        try:  # reference binding: start_point == (row, col)
            return int(_call(node.start_point)[0]) + 1
        except Exception:
            return 1


def children(node: Any) -> list:
    try:
        n = _call(node.child_count)
        return [node.child(i) for i in range(n)]
    except Exception:
        return list(_call(node.children))


def named_children(node: Any) -> list:
    try:
        n = _call(node.named_child_count)
        return [node.named_child(i) for i in range(n)]
    except Exception:
        return [c for c in children(node) if _call(c.is_named)]


def field_child(node: Any, name: str) -> Optional[Any]:
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def walk(node: Any) -> Iterator[Any]:
    """Depth-first iterate over ``node`` and all its descendants."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        stack.extend(reversed(children(cur)))


def find(node: Any, kinds: Iterable[str]) -> list:
    wanted = set(kinds)
    return [n for n in walk(node) if kind(n) in wanted]


# --------------------------------------------------------------------------- #
# Unified diff parsing
# --------------------------------------------------------------------------- #
@dataclass
class Hunk:
    added: list[str]     # content of '+' lines (without leading '+')
    removed: list[str]   # content of '-' lines (without leading '-')


def _iter_body_lines(diff_text: str) -> Iterator[str]:
    for ln in diff_text.splitlines():
        if ln.startswith(("+++", "---", "diff ", "index ", "@@", "new file",
                          "deleted file", "rename ", "similarity ", "\\ No newline")):
            continue
        yield ln


def added_lines(diff_text: str) -> list[str]:
    return [ln[1:] for ln in _iter_body_lines(diff_text) if ln.startswith("+")]


def iter_added(diff_text: str) -> list[tuple[Optional[int], str]]:
    """Yield ``(new_file_lineno, content)`` for every added ('+') line.

    Line numbers are recovered from ``@@ -a,b +c,d @@`` hunk headers so evidence
    can point at a concrete line. Falls back to ``None`` if headers are absent.
    """
    import re

    out: list[tuple[Optional[int], str]] = []
    cur: Optional[int] = None
    header = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    for ln in diff_text.splitlines():
        m = header.match(ln)
        if m:
            cur = int(m.group(1))
            continue
        if ln.startswith("+++") or ln.startswith("---"):
            continue
        if ln.startswith("+"):
            out.append((cur, ln[1:]))
            if cur is not None:
                cur += 1
        elif ln.startswith("-"):
            continue  # removed lines don't advance the new-file counter
        else:
            if cur is not None:
                cur += 1  # context line
    return out


def removed_lines(diff_text: str) -> list[str]:
    return [ln[1:] for ln in _iter_body_lines(diff_text) if ln.startswith("-")]


def parse_hunks(diff_text: str) -> list[Hunk]:
    hunks: list[Hunk] = []
    cur: Optional[Hunk] = None
    for ln in diff_text.splitlines():
        if ln.startswith("@@"):
            cur = Hunk(added=[], removed=[])
            hunks.append(cur)
            continue
        if ln.startswith(("+++", "---", "diff ", "index ", "new file",
                          "deleted file", "rename ", "similarity ", "\\ No newline")):
            continue
        if cur is None:
            cur = Hunk(added=[], removed=[])
            hunks.append(cur)
        if ln.startswith("+"):
            cur.added.append(ln[1:])
        elif ln.startswith("-"):
            cur.removed.append(ln[1:])
    return hunks


# --------------------------------------------------------------------------- #
# Net-diff reconstruction
# --------------------------------------------------------------------------- #
def _normalize_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def net_file_diffs(task: Any, trajectory: Trajectory, sandbox: Any) -> list[FileDiff]:
    """Return the *net* per-file diff for the whole attempt.

    Priority:
      1. ``sandbox.diff(initial, final)`` — the authoritative net diff.
      2. reconstruction by folding every step's ``file_diffs`` in order.

    Either way the result is one ``FileDiff`` per touched path, carrying the true
    before/after blobs where available. Robust to a missing or partial sandbox.
    """
    # 1) authoritative sandbox diff
    init_id = getattr(trajectory, "initial_snapshot_id", None)
    final_id = getattr(trajectory, "final_snapshot_id", None)
    if sandbox is not None and init_id and final_id:
        differ = getattr(sandbox, "diff", None)
        if callable(differ):
            try:
                diffs = differ(init_id, final_id)
                if diffs:
                    return list(diffs)
            except Exception:
                pass

    # 2) fold trajectory steps
    return fold_step_diffs(trajectory)


def fold_step_diffs(trajectory: Trajectory) -> list[FileDiff]:
    """Collapse per-step ``FileDiff``s into one net ``FileDiff`` per path."""
    first_before: dict[str, Optional[str]] = {}
    first_change: dict[str, str] = {}
    last_after: dict[str, Optional[str]] = {}
    last_change: dict[str, str] = {}
    diff_texts: dict[str, list[str]] = {}
    order: list[str] = []

    for step in getattr(trajectory, "steps", []) or []:
        for fd in getattr(step, "file_diffs", []) or []:
            key = fd.path
            if key not in first_before:
                first_before[key] = fd.before_blob
                first_change[key] = fd.change_type
                diff_texts[key] = []
                order.append(key)
            last_after[key] = fd.after_blob
            last_change[key] = fd.change_type
            if fd.diff_text:
                diff_texts[key].append(fd.diff_text)

    out: list[FileDiff] = []
    for key in order:
        fc, lc = first_change[key], last_change[key]
        if lc == "deleted":
            net = "deleted"
        elif fc == "added" and lc != "deleted":
            net = "added"
        else:
            net = "modified"
        out.append(FileDiff(
            path=key,
            change_type=net,
            diff_text="\n".join(diff_texts[key]),
            before_blob=first_before[key],
            after_blob=last_after.get(key),
        ))
    return out


def matches_any(path: str, patterns: Iterable[str]) -> bool:
    """Path match against a list of exact paths / prefixes / fnmatch globs.

    Also matches when one path is a *component-aligned suffix* of the other, so a
    pattern declared relative to the task dir (e.g. ``repo/monitor.py``) still
    matches a diff path that is relative to the repo workdir (``monitor.py``), and
    vice-versa. The suffix must align on a ``/`` boundary — ``repo/monitor.py``
    matches ``monitor.py`` but never ``evil_monitor.py`` — so this stays precise
    and does not manufacture false positives.
    """
    import fnmatch

    np = _normalize_path(path)
    for pat in patterns:
        p = _normalize_path(str(pat))
        if np == p:
            return True
        if p.endswith("/") and np.startswith(p):
            return True
        if fnmatch.fnmatch(np, p) or fnmatch.fnmatch(np, p + "/*") or fnmatch.fnmatch(np, "*/" + p):
            return True
        if np.startswith(p.rstrip("/") + "/"):
            return True
        # component-aligned suffix match (handles repo_relpath prefix skew, e.g.
        # pattern "repo/monitor.py" vs diff path "monitor.py")
        if not p.endswith("/") and (np.endswith("/" + p) or p.endswith("/" + np)):
            return True
    return False
