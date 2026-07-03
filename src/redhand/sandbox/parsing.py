"""Test-output parsing for the sandbox.

``parse_test_output`` turns a captured test run's combined stdout+stderr into a
``(passed, failed, total)`` triple, handling the common runners:

  * **pytest** — "3 passed, 1 failed in 0.12s", "5 passed", "1 error".
  * **node --test** (TAP) — "# tests 4", "# pass 3", "# fail 1".
  * **mocha** — "3 passing", "1 failing".
  * **jest / vitest** — "Tests: 1 failed, 2 passed, 3 total".

Returns ``None`` when nothing recognizable is found, so the caller can fall back
to the process exit code.
"""

from __future__ import annotations

import re
from typing import Optional

# ------------------------------------------------------------------ #
# individual runner parsers: each returns (passed, failed, total) or None
# ------------------------------------------------------------------ #

def _parse_jest(text: str) -> Optional[tuple[int, int, int]]:
    # "Tests:       1 failed, 2 passed, 3 total"
    for line in text.splitlines():
        if "Tests:" not in line:
            continue
        m_total = re.search(r"(\d+)\s+total", line)
        if not m_total:
            continue
        passed = _num(re.search(r"(\d+)\s+passed", line))
        failed = _num(re.search(r"(\d+)\s+failed", line))
        return passed, failed, int(m_total.group(1))
    return None


def _parse_node_tap(text: str) -> Optional[tuple[int, int, int]]:
    m_tests = re.search(r"^#\s*tests\s+(\d+)", text, re.MULTILINE)
    m_pass = re.search(r"^#\s*pass\s+(\d+)", text, re.MULTILINE)
    m_fail = re.search(r"^#\s*fail\s+(\d+)", text, re.MULTILINE)
    if not (m_tests or m_pass or m_fail):
        return None
    passed = _num(m_pass)
    failed = _num(m_fail)
    total = int(m_tests.group(1)) if m_tests else passed + failed
    return passed, failed, total


def _parse_mocha(text: str) -> Optional[tuple[int, int, int]]:
    m_pass = re.search(r"(\d+)\s+passing", text)
    m_fail = re.search(r"(\d+)\s+failing", text)
    if not (m_pass or m_fail):
        return None
    passed = _num(m_pass)
    failed = _num(m_fail)
    return passed, failed, passed + failed


def _parse_pytest(text: str) -> Optional[tuple[int, int, int]]:
    # Sum every "<N> <status>" token pytest emits in its summary line(s).
    passed = failed = skipped = 0
    found = False
    for count, status in re.findall(
        r"(\d+)\s+(passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)",
        text,
    ):
        n = int(count)
        if status in ("passed", "xpassed"):
            passed += n
            found = True
        elif status in ("failed", "error", "errors"):
            failed += n
            found = True
        elif status in ("skipped", "xfailed"):
            skipped += n
            found = True
        # 'deselected' / 'warnings' are not test outcomes -> ignored
    if not found:
        return None
    return passed, failed, passed + failed + skipped


def _num(m: Optional[re.Match]) -> int:
    return int(m.group(1)) if m else 0


# Order matters: try the most specific / unambiguous formats first.
_PARSERS = (_parse_jest, _parse_node_tap, _parse_mocha, _parse_pytest)


def parse_test_output(text: str) -> Optional[tuple[int, int, int]]:
    """Return (passed, failed, total) parsed from test output, or None."""
    if not text:
        return None
    for parser in _PARSERS:
        result = parser(text)
        if result is not None and (result[0] or result[1] or result[2]):
            return result
    return None
