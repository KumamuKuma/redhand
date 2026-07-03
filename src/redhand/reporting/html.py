"""redhand — static, fully-offline HTML dashboard.

Renders a single self-contained HTML file (CSS + JS inlined, **no external
CDN / fonts / images / network at all**) that a reviewer can open by
double-clicking (``file://``). Contents:

* a leaderboard,
* a scorecard per agent,
* a trajectory *replay* for every flagged run (step-by-step tool calls + file
  diffs), with the sabotage (S-) tags that were hit highlighted in red.

Only consumes :class:`Trajectory` / :class:`DetectionResult` and the scoring
aggregates — never touches the engine.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from redhand.contracts import DetectionResult, SabotageTag, Trajectory
from redhand.scoring import (
    ScoringResult,
    aggregate,
    index_detections,
    short_tag,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

_GRADE_CLASS = {"A": "a", "B": "b", "C": "c", "D": "d", "F": "f"}


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


# --------------------------------------------------------------------------- #
# Diff rendering
# --------------------------------------------------------------------------- #
def classify_diff(diff_text: str) -> list[dict]:
    """Split a unified diff into classified lines for CSS styling."""
    out: list[dict] = []
    for line in (diff_text or "").splitlines():
        if line.startswith("@@"):
            kind = "hunk"
        elif line.startswith("+++") or line.startswith("---"):
            kind = "meta"
        elif line.startswith("+"):
            kind = "add"
        elif line.startswith("-"):
            kind = "del"
        else:
            kind = "ctx"
        out.append({"kind": kind, "text": line})
    return out


def _tool_arg_summary(arguments: dict) -> str:
    """One-line, human-readable summary of a tool call's arguments."""
    if not arguments:
        return ""
    parts = []
    for k, v in arguments.items():
        s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
        if len(s) > 120:
            s = s[:117] + "..."
        parts.append(f"{k}={s}")
    return "  ".join(parts)


def _tag_info(tag: SabotageTag) -> dict:
    return {
        "value": tag.value,
        "code": short_tag(tag),
        "description": tag.description,
    }


def _is_flagged(traj: Trajectory, det: Optional[DetectionResult]) -> bool:
    cheated = bool(det and det.cheated)
    return cheated or (traj.claimed_success and not traj.truly_succeeded)


def _reasons(traj: Trajectory, det: Optional[DetectionResult]) -> list[str]:
    reasons: list[str] = []
    cheated = bool(det and det.cheated)
    if traj.claimed_success and cheated:
        reasons.append("Deceptive: claimed success while cheating")
    elif traj.claimed_success and not traj.truly_succeeded:
        reasons.append("Deceptive: claimed success but hidden tests failed")
    if cheated:
        reasons.append("Sabotage detected")
    if not traj.truly_succeeded:
        reasons.append("Hidden tests failed")
    return reasons


def _build_failure_case(traj: Trajectory, det: Optional[DetectionResult]) -> dict:
    evidences = det.evidences if det else []
    flagged_files = {e.file for e in evidences if e.file}
    tags = sorted({e.tag for e in evidences}, key=lambda t: short_tag(t))

    steps = []
    for s in traj.steps:
        tc = s.tool_call
        cmd = s.command
        diffs = [
            {
                "path": d.path,
                "change_type": d.change_type,
                "flagged": d.path in flagged_files,
                "lines": classify_diff(d.diff_text),
            }
            for d in s.file_diffs
        ]
        steps.append(
            {
                "index": s.index,
                "tool": tc.name if tc else None,
                "tool_args": _tool_arg_summary(tc.arguments) if tc else "",
                "command": (
                    {
                        "command": cmd.command,
                        "exit_code": cmd.exit_code,
                        "ok": cmd.exit_code == 0,
                        "stdout": cmd.stdout,
                        "stderr": cmd.stderr,
                    }
                    if cmd
                    else None
                ),
                "diffs": diffs,
                "note": s.note,
            }
        )

    return {
        "agent": traj.agent,
        "task_id": traj.task_id,
        "run_index": traj.run_index,
        "claimed": traj.claimed_success,
        "truly": traj.truly_succeeded,
        "reasons": _reasons(traj, det),
        "tags": [_tag_info(t) for t in tags],
        "evidences": [
            {
                "code": short_tag(e.tag),
                "tag": e.tag.value,
                "detector": e.detector_name,
                "deterministic": e.deterministic,
                "confidence": e.confidence,
                "file": e.file,
                "line": e.line,
                "snippet": e.snippet,
                "explanation": e.explanation,
            }
            for e in evidences
        ],
        "steps": steps,
    }


def build_context(result: ScoringResult, trajectories, detection_results, title: str) -> dict:
    dets = index_detections(detection_results)

    failure_cases = []
    for t in sorted(trajectories, key=lambda x: (x.agent, x.task_id, x.run_index)):
        det = dets.get((t.task_id, t.agent, t.run_index))
        if _is_flagged(t, det):
            failure_cases.append(_build_failure_case(t, det))

    agents = []
    for s in result.agents:
        agents.append(
            {
                "agent": s.agent,
                "n_tasks": s.n_tasks,
                "runs_per_task": s.runs_per_task_label,
                "true_success": s.mean_true_success,
                "claimed_success": s.mean_claimed_success,
                "deceptive_success": s.mean_deceptive_success,
                "cheat_rate": s.mean_cheat_rate,
                "recovery": s.mean_recovery_score,
                "cost": s.mean_cost_usd,
                "grade": s.safety_grade,
                "grade_class": _GRADE_CLASS.get(s.safety_grade, "f"),
                "tag_counts": [
                    {"code": short_tag(tag), "tag": tag, "count": c}
                    for tag, c in sorted(s.tag_counts.items(), key=lambda kv: short_tag(kv[0]))
                ],
            }
        )

    leaderboard = [
        {
            "rank": i,
            "agent": r.agent,
            "n_tasks": r.n_tasks,
            "true_success": r.mean_true_success,
            "cheat_rate": r.mean_cheat_rate,
            "deceptive_success": r.mean_deceptive_success,
            "cost": r.mean_cost_usd,
            "grade": r.safety_grade,
            "grade_class": _GRADE_CLASS.get(r.safety_grade, "f"),
        }
        for i, r in enumerate(result.leaderboard, 1)
    ]

    return {
        "title": title,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "leaderboard": leaderboard,
        "agents": agents,
        "failure_cases": failure_cases,
        "n_flagged": len(failure_cases),
        "n_agents": len(agents),
    }


def render_dashboard(
    trajectories: Iterable[Trajectory],
    detection_results: Iterable[DetectionResult] = (),
    *,
    title: str = "redhand — agent safety dashboard",
    result: Optional[ScoringResult] = None,
) -> str:
    """Render the dashboard to a single self-contained HTML string."""
    trajectories = list(trajectories)
    detection_results = list(detection_results)
    if result is None:
        result = aggregate(trajectories, detection_results)

    env = _env()
    styles = (TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
    script = (TEMPLATES_DIR / "app.js").read_text(encoding="utf-8")
    template = env.get_template("dashboard.html.j2")
    context = build_context(result, trajectories, detection_results, title)
    context["styles"] = styles
    context["script"] = script
    return template.render(**context)


def write_dashboard(
    path: str | Path,
    trajectories: Iterable[Trajectory],
    detection_results: Iterable[DetectionResult] = (),
    *,
    title: str = "redhand — agent safety dashboard",
) -> Path:
    """Render and write the dashboard; returns the written path."""
    html = render_dashboard(trajectories, detection_results, title=title)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
