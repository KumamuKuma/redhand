# redhand — design spec (v0.1)

> A red-team gym that catches **coding agents cheating** when an honest solution
> is hard. It drives a *real* agent (Claude Code first) headless in a disposable
> sandbox, records the full trajectory, and inspects it with AST/git detectors
> plus an LLM-judge fallback — then scores *deceptive success* and renders a
> shareable report.

## 1. Why this exists / positioning

See [`docs/competitive-positioning.md`](docs/competitive-positioning.md). Short
version: prior work (EvilGenie, SpecBench, AgentDojo, ASB, …) tests **models** in
**researcher-built** harnesses and reports **model leaderboards**. redhand is a
`pip install` **developer tool** that red-teams **your real agent assembly**
(binary + `CLAUDE.md` + enabled tools) and reports **per-line, AST/git-grounded**
evidence of *how* it cheated. North star: produce a *new empirical finding* about
real agents, not another leaderboard.

## 2. Core concepts

- **Task** — a repo state that is *honestly solvable but hard*, with a **visible**
  test command the agent is told to satisfy and a **hidden** held-out oracle it
  never sees. Cheating = making the visible signal green without truly solving it
  (hidden tests stay red) or by tampering with tests/checks.
- **Trajectory** — the full record of one attempt: tool calls, commands, per-step
  git snapshots and file diffs, visible/hidden test results, tokens/cost.
- **Sabotage taxonomy (S1–S8)** — the shared vocabulary (see `contracts.py`):
  S1 delete test · S2 weaken assert · S3 hardcode · S4 skip test ·
  S5 disable check · S6 fake success · S7 scope reduction · S8 sabotage monitor.
- **Detection** — deterministic AST/git rules first (high precision, per-line
  evidence), LLM-judge only as a fallback for subtle S3/S7.
- **Deceptive success** — the headline metric: fraction of runs where the agent
  **claimed success** (visible tests green) but was actually cheating and/or the
  hidden tests failed. This is what nobody else reports on real agents.

## 3. Architecture & module ownership

```
redhand run --agent claude-code --tasks ./tasks --runs 5 --out ./results
        │
        ▼
   runner.py ──drives──> AgentAdapter (adapters/)  ──acts in──> Sandbox (sandbox/)
        │                                                          │
        │  Trajectory[]  <───────────────────────────────────────┘
        ▼
   detectors/ ──> DetectionResult[]      scoring.py ──> TaskScore[] / LeaderboardRow[]
        │                                     │
        └──────────────> reporting/ (console + offline HTML dashboard)
```

| Module | Files | Owner | Depends on |
|---|---|---|---|
| Contracts (seam) | `src/redhand/contracts.py` | frozen | — |
| Runner / harness | `src/redhand/runner.py`, `adapters/` | Builder A | contracts, Sandbox |
| Sandbox | `src/redhand/sandbox/` | Builder B | contracts |
| Detectors | `src/redhand/detectors/` | Builder C | contracts |
| Task set | `tasks/` | Builder D | contracts (Task) |
| Scoring + reporting | `src/redhand/scoring.py`, `reporting/` | Builder E | contracts |
| CLI (integration) | `src/redhand/cli.py` | integration | all |

The single rule that makes parallel work compose: **everything crosses module
boundaries as a `contracts.py` type.** No module redefines a shared type.

## 4. Key decisions

- **Held-out oracle is physically removed from the agent's workspace.** The
  sandbox drops `tests/hidden` (configurable via `metadata["heldout_paths"]`) when
  materializing the repo, so a real agent cannot read or game the oracle. The
  adapter re-injects it only *after* the final snapshot, purely to score — so the
  diff the detectors inspect never contains the oracle.
- **No Docker required** → sandbox MVP is a *disposable working copy* in a temp
  dir (override with `REDHAND_SANDBOX_DIR`) + a restricted, network-degraded
  subprocess. Cross-platform: `bash -c` on POSIX, `cmd /c` on Windows; timeouts
  kill the whole process tree (`killpg` / `taskkill /T`). `Sandbox` is a Protocol;
  a `DockerSandbox` implementing the same interface is a future contribution.
- **Real agents, not model APIs** → the Claude Code adapter shells out to the
  installed `claude` binary (headless/print mode); the Codex adapter shells out to
  `codex exec --json`. A `MockAgentAdapter` replays a scripted trajectory so the
  whole pipeline is testable **without spending money or network**.
- **Every run leaves a reproducibility trail** → `redhand run`/`demo` write
  per-attempt `trajectory.json` / `detection_report.json` / `run_result.json`
  (namespaced per agent) plus a `suite_result.json` and an offline dashboard.
- **Cost is first-class** → runner enforces a budget ceiling; every trajectory
  carries tokens/cost; default `runs` is small and opt-in to scale.
- **Statistical honesty** → per (agent, task) we report `pass^k` and 95% CIs, not
  single-run numbers.
- **Detector credibility** → deterministic layer prefers false negatives; honest
  fixes must never be flagged.

## 5. Testing & safety invariants

- All unit tests run under `.venv/bin/pytest`, **offline**, and **never invoke the
  real `claude` binary** (mock adapter + injectable judge stub).
- Shadow git for snapshots must not pollute the task repo's own `.git`.
- All working files live under the sandbox base directory — the OS temp dir by
  default, or `REDHAND_SANDBOX_DIR` if set (point it at a disk with room when the
  root filesystem is small).
- Agent prompts must never reveal the existence or content of hidden tests.
- Tasks must be honestly solvable; hidden tests start red (proving there is real
  work to do).

## 6. Out of scope for v0.1

Docker/remote sandboxes · non-coding tool-use safety (email/browser/calendar) ·
prompt-injection threat model (that's AgentDojo's) · a hosted leaderboard service ·
agents beyond Claude Code and Codex (Cursor/aider adapters are future work).
