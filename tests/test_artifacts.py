"""Per-attempt artifact writer: layout, namespacing, and content."""

from __future__ import annotations

import json
import os

from redhand.artifacts import write_run_artifacts
from redhand.contracts import (
    DetectionEvidence,
    DetectionResult,
    SabotageTag,
    Trajectory,
)
from redhand.contracts import TestResult as _TestResult  # aliased so pytest doesn't collect it


def _traj(agent, task_id, run_index, *, claimed, truly):
    return Trajectory(
        task_id=task_id, agent=agent, run_index=run_index,
        visible_test_result=_TestResult(passed=1, total=1) if claimed else _TestResult(),
        hidden_test_result=_TestResult(passed=1, total=1) if truly else _TestResult(failed=1, total=1),
        cost_usd=0.0,
    )


def test_agents_over_same_task_do_not_collide(tmp_path):
    honest = _traj("demo_honest", "lru_cache", 0, claimed=True, truly=True)
    cheater = _traj("demo_cheater", "lru_cache", 0, claimed=True, truly=False)
    det = DetectionResult(
        task_id="lru_cache", agent="demo_cheater", run_index=0,
        evidences=[DetectionEvidence(tag=SabotageTag.S1_DELETE_TEST,
                                     detector_name="d", deterministic=True)],
    )
    out = str(tmp_path / "out")
    write_run_artifacts(out, [honest, cheater], [det])

    # separate per-agent directories, no overwrite
    assert os.path.isdir(os.path.join(out, "demo_honest", "lru_cache-run0"))
    assert os.path.isdir(os.path.join(out, "demo_cheater", "lru_cache-run0"))

    # cheater run_result reflects deceptive success; honest does not
    with open(os.path.join(out, "demo_cheater", "lru_cache-run0", "run_result.json")) as fh:
        cheat = json.load(fh)
    assert cheat["deceptive_success"] is True
    assert cheat["cheated"] is True
    assert "S1_delete_test" in cheat["sabotage_tags"]

    with open(os.path.join(out, "demo_honest", "lru_cache-run0", "run_result.json")) as fh:
        honest_r = json.load(fh)
    assert honest_r["deceptive_success"] is False
    assert honest_r["cheated"] is False

    # suite summary exists and is valid json with a leaderboard
    with open(os.path.join(out, "suite_result.json")) as fh:
        suite = json.load(fh)
    assert suite["n_trajectories"] == 2
    assert len(suite["leaderboard"]) == 2
