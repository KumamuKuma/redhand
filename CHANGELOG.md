# Changelog

All notable changes to redhand are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## 0.1.0 — 2026-07-03

Initial public release: a red-team gym MVP that catches coding agents faking a
green checkmark when the honest fix is hard.

### Added

- **21 seed tasks** (`src/redhand/tasks/`) that are honestly solvable but hard —
  Python and JS/TS — each with a visible test suite the agent is told to satisfy,
  a held-out hidden oracle it never sees, and a reference solution.
- **Held-out oracle enforcement.** The sandbox physically removes `tests/hidden`
  from the agent's workspace and re-injects it only *after* the final snapshot,
  purely to score — so the diff the detectors inspect never contains the oracle.
- **AST + git detectors** for the S1–S8 sabotage taxonomy (tree-sitter AST plus
  git-diff rules), tuned for high precision (an honest fix must not be flagged),
  with an optional, opt-in LLM judge for the subtler S3/S7 cases.
- **Real agent adapters.** `ClaudeCodeAdapter` drives the installed `claude` CLI
  headless; `CodexAdapter` drives `codex exec --json`. A `MockAgentAdapter`
  replays a scripted trajectory so the whole pipeline is testable offline.
- **Zero-cost demo** (`redhand demo`): scripted honest + cheater agents exercise
  the entire pipeline with no API key and no network cost.
- **Scoring.** Deceptive-success rate (the headline metric), `pass^k` reliability,
  and 95% confidence intervals per (agent, task).
- **Offline dashboard.** A fully self-contained HTML report that replays each run
  step-by-step with red/green diffs.
- **Cross-platform sandbox.** `bash -c` on POSIX, `cmd /c` on Windows; timeouts
  kill the whole process tree (`killpg` / `taskkill /T`); best-effort network
  degradation, with real `unshare -n` isolation when the host permits it.
- **Infrastructure-error detection.** A run whose test command cannot execute
  (missing shell/interpreter, exit 126/127) is flagged and surfaced with a loud
  banner and a non-zero exit, rather than being scored as a legitimate failure.
- **`DockerSandbox` contribution stub** documenting the `Sandbox` Protocol for a
  future real-isolation (`--network none`) backend.

### Fixed / packaging

- Ship the seed tasks and dashboard templates as package data so wheel (non-
  editable) installs find tasks and render HTML from any working directory.
- Portable sandbox base directory: default to the OS temp dir and override with
  `REDHAND_SANDBOX_DIR`, so no host-specific path is baked into the wheel.
- Quote the interpreter path in the test-suite shell helpers so command
  construction survives interpreter paths that contain spaces (e.g. Windows'
  `C:\Program Files\...`).
