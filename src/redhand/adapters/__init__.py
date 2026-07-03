"""redhand agent adapters.

Each adapter implements the :class:`redhand.contracts.AgentAdapter` protocol —
driving *some* coding agent headless over one task in a sandbox and returning a
``Trajectory``.

* :class:`MockAgentAdapter` — deterministic, offline, free; replays a scripted
  list of tool actions. Use it for tests and pipeline integration.
* :class:`ClaudeCodeAdapter` — drives the real ``claude`` CLI in headless print
  mode.
* :class:`CodexAdapter` — drives the real ``codex`` CLI via ``codex exec``.
"""

from redhand.adapters.base import AdapterBase, safe_diff, safe_snapshot
from redhand.adapters.claude_code import ClaudeCodeAdapter, consume_stream_json
from redhand.adapters.codex import CodexAdapter, consume_codex_json
from redhand.adapters.mock import MockAgentAdapter

__all__ = [
    "AdapterBase",
    "MockAgentAdapter",
    "ClaudeCodeAdapter",
    "consume_stream_json",
    "CodexAdapter",
    "consume_codex_json",
    "safe_snapshot",
    "safe_diff",
]
