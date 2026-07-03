"""Portable shell-command builders for the test suite.

Tests exercise real command execution through the sandbox, which runs commands
under bash on POSIX and cmd on Windows. POSIX-only tools such as true, grep,
test -f, printf, sleep, and seq do not exist on cmd.exe, so tests express these
commands as short Python one-liners via the current interpreter.

Quoting: the interpreter path is double-quoted so paths containing spaces
survive. Python's Windows subprocess(..., shell=True) preserves that quoted
executable; adding another pair of outer quotes breaks cmd.exe parsing. The -c
code must be a one-line string that uses single-quoted string literals and no
shell metacharacters such as >, <, |, &, %, or !.
"""

from __future__ import annotations

import os
import sys

_PY = sys.executable
_IS_WINDOWS = os.name == "nt"


def py(code: str) -> str:
    return f'"{_PY}" -c "{code}"'


# exit 0 / exit 1 with no parseable test counts (fallback path)
TRUE = py("import sys; sys.exit(0)")
FALSE = py("import sys; sys.exit(1)")


def sleep(seconds) -> str:
    return py(f"import time; time.sleep({seconds})")


def isfile(path: str) -> str:
    return py(f"import os, sys; sys.exit(0 if os.path.isfile('{path}') else 1)")


def contains(needle: str, path: str) -> str:
    return py(
        f"import sys; sys.exit(0 if '{needle}' in "
        f"open('{path}', encoding='utf-8').read() else 1)"
    )


def write(path: str, content: str) -> str:
    return py(f"open('{path}', 'w', encoding='utf-8').write('{content}')")


def write_and_print(path: str, content: str) -> str:
    return py(
        f"open('{path}', 'w', encoding='utf-8').write('{content}'); "
        f"print(open('{path}', encoding='utf-8').read())"
    )


def print_many(n: int, token: str = "LINE") -> str:
    return py(f"[print('{token}' + str(i)) for i in range({n})]")
