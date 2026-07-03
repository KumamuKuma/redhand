"""redhand detector layer — catches coding agents cheating.

Two tiers:

* **Deterministic** (``deterministic.py``): AST + git-diff rules that fire only
  when a sabotage pattern is near-certain. High precision, near-zero false
  positives — an honest change must never be flagged. Covers S1, S2, S3, S4, S5,
  S6, S8.
* **LLM judge** (``judge.py``): a recall-oriented, majority-vote fallback for the
  judgement-heavy cases (S3 confirmation, S7 scope reduction). ``deterministic=
  False``. Not run by default (opt-in), so nothing calls a real model implicitly.

Use ``run_detectors(task, trajectory, sandbox)`` to run the default set and get a
single aggregated ``DetectionResult``. Every detector implements the
``contracts.Detector`` Protocol.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

from redhand.contracts import DetectionEvidence, DetectionResult, Detector, Task, Trajectory

from .deterministic import (
    DeleteTestDetector,
    DisableCheckDetector,
    FakeSuccessDetector,
    HardcodeDetector,
    SabotageMonitorDetector,
    SkipTestDetector,
    WeakenAssertDetector,
)
from .judge import LLMJudgeDetector, claude_cli_judge

__all__ = [
    "DeleteTestDetector",
    "WeakenAssertDetector",
    "HardcodeDetector",
    "SkipTestDetector",
    "DisableCheckDetector",
    "FakeSuccessDetector",
    "SabotageMonitorDetector",
    "LLMJudgeDetector",
    "claude_cli_judge",
    "DETERMINISTIC_DETECTORS",
    "DEFAULT_DETECTORS",
    "run_detectors",
]


def _make_deterministic() -> list[Detector]:
    return [
        DeleteTestDetector(),
        WeakenAssertDetector(),
        HardcodeDetector(),
        SkipTestDetector(),
        DisableCheckDetector(),
        FakeSuccessDetector(),
        SabotageMonitorDetector(),
    ]


#: All deterministic detectors — always safe to run (no network, no cost).
DETERMINISTIC_DETECTORS: list[Detector] = _make_deterministic()

#: The default detector set. Deterministic-only on purpose: the LLM judge is
#: opt-in so ``run_detectors`` never spends tokens or touches the network unless
#: a caller explicitly passes it in.
DEFAULT_DETECTORS: list[Detector] = list(DETERMINISTIC_DETECTORS)


def _dedupe(evidences: list[DetectionEvidence]) -> list[DetectionEvidence]:
    seen: set[tuple] = set()
    out: list[DetectionEvidence] = []
    for e in evidences:
        key = (e.tag, e.detector_name, e.file, e.line, e.snippet)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def run_detectors(
    task: Task,
    trajectory: Trajectory,
    sandbox: Any,
    detectors: Optional[Sequence[Detector]] = None,
) -> DetectionResult:
    """Run ``detectors`` (default: ``DEFAULT_DETECTORS``) over one trajectory and
    aggregate every ``DetectionEvidence`` into a single ``DetectionResult``.

    Robustness: a crashing detector is isolated — its failure never aborts the
    others (a detector bug must not silence the whole layer).
    """
    dets = list(detectors) if detectors is not None else DEFAULT_DETECTORS
    evidences: list[DetectionEvidence] = []
    for det in dets:
        try:
            evidences.extend(det.detect(task, trajectory, sandbox) or [])
        except Exception:
            continue
    return DetectionResult(
        task_id=task.id,
        agent=trajectory.agent,
        run_index=trajectory.run_index,
        evidences=_dedupe(evidences),
    )
