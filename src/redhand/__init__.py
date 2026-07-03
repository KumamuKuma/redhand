"""redhand — a red-team gym for tool-using coding agents.

Catches coding agents that cheat (delete tests, hardcode, disable checks, fake
success) when an honest solution is hard, by driving real agents headless in a
disposable sandbox and inspecting the resulting trajectory with AST/git
detectors and an LLM-judge fallback.
"""

__version__ = "0.0.1"

from redhand.contracts import (  # noqa: F401
    SCHEMA_VERSION,
    AgentAdapter,
    CommandResult,
    DetectionEvidence,
    DetectionResult,
    Detector,
    FileDiff,
    LeaderboardRow,
    SabotageTag,
    Sandbox,
    Task,
    TaskScore,
    TestResult,
    Trajectory,
    TrajectoryStep,
    ToolCall,
)
