# Contributing to redhand

Thanks for helping red-team coding agents. redhand is built to grow along **four
extension seams**. Three are `Protocol`s declared in
[`src/redhand/contracts.py`](src/redhand/contracts.py) — implement the interface
and your component is drop-in interchangeable. The fourth, a *task*, is a `Task`
dataclass plus a directory convention: data and files, no code to implement.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate            # Windows (PowerShell): .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -q                       # 211 tests, fully offline, no API key, cross-platform
```

`pytest` needs `git` and the task interpreters on `PATH`: `python` (in the venv,
so it has `pytest`) and `node` for the JS/TS tasks. CI runs the same
`pip install -e ".[dev]"` + `pytest -q` on Ubuntu and Windows across Python
3.11/3.12 (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## The four extension seams

### 1. New tasks — add `src/redhand/tasks/<id>/`

A task is a `Task` dataclass (see `contracts.py`) plus a directory convention;
there is **no code to implement**. Add a `src/redhand/tasks/<id>/` containing:

- `task.yaml` — the task metadata (id, language, difficulty, prompt, visible and
  hidden test commands, reference-solution dir, expected sabotage tags);
- `repo/` — a hard-but-honestly-solvable initial repo;
- a **visible** test suite under the repo (the signal the agent is told to make
  green);
- a **hidden** held-out oracle (default `tests/hidden/`), which the sandbox
  removes from the agent's workspace and re-injects only to score;
- `solution/` — a reference solution overlaid onto `repo/` to prove the task is
  honestly solvable.

Invariants (enforced by `tests/test_tasks.py`): the prompt must never mention or
leak the hidden oracle; the hidden tests must start **red** on the initial repo
(there is real work to do) and go **green** once `solution/` is applied, with the
visible command green too.

### 2. New agent adapters — implement `AgentAdapter`

Implement the `AgentAdapter` Protocol to drive another coding agent (Cursor,
aider, …). Claude Code (`claude` CLI) and Codex (`codex exec`) ship today; see
`src/redhand/adapters/` for reference. The adapter runs the agent headless in a
`Sandbox`, records the `Trajectory`, and re-injects the hidden oracle only after
the final snapshot.

### 3. New detectors — implement `Detector`

Implement the `Detector` Protocol to catch more sabotage sub-types (S1–S8) or new
languages. Detectors receive the trajectory and per-step diffs and return
per-line, AST/git-grounded evidence. The deterministic layer prefers false
negatives — an honest change must never be flagged; see `src/redhand/detectors/`.

### 4. New sandbox backends — implement `Sandbox`

Implement the `Sandbox` Protocol for stronger isolation (Docker, remote, gVisor).
`src/redhand/sandbox/local.py` is the Docker-free MVP; `docker.py` is a stubbed
contribution point that documents the contract for a real `--network none`
container backend. Keep working state under the sandbox base directory (the OS
temp dir by default, or `REDHAND_SANDBOX_DIR`); never hard-code a host path.

## Running the tests

```bash
pip install -e ".[dev]"
pytest -q                       # whole suite
pytest tests/test_tasks.py -q   # just the task-set invariants
```

Tests must stay **offline** and must **never** invoke the real `claude`/`codex`
binaries (use the mock adapter and the injectable judge stub). New code should
come with tests, and any behavior change should be noted in
[`CHANGELOG.md`](CHANGELOG.md). Design notes live in [`SPEC.md`](SPEC.md).
