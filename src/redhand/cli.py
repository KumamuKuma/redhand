"""redhand command-line interface.

    redhand demo   [--tasks DIR] [--limit N] [--task ID] [--out DIR]
    redhand run    --agent claude-code [--tasks DIR] [--runs K] [--task ID]
                   [--limit N] [--model M] [--max-cost USD] [--out DIR]
    redhand list   [--tasks DIR]

``demo`` needs no API key or network: two scripted stand-in agents (honest +
cheater) exercise the whole pipeline so you can see deceptive success caught.
``run`` drives the real ``claude`` CLI and **spends money** — start small.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from redhand import __version__
from redhand.artifacts import write_run_artifacts
from redhand.evaluate import evaluate
from redhand.reporting import print_report, write_dashboard
from redhand.taskset import default_tasks_dir, load_tasks

_AGENTS = ("claude-code", "codex")

_DEFAULT_OUT = "results"


def _resolve_tasks_dir(path: Optional[str]) -> str:
    # explicit --tasks wins; otherwise use the bundled seed tasks (works from any
    # cwd, editable or wheel install).
    if path:
        if os.path.isdir(path):
            return path
        raise SystemExit(f"tasks directory not found: {path!r}")
    bundled = default_tasks_dir()
    if os.path.isdir(bundled):
        return bundled
    raise SystemExit(f"bundled tasks directory missing: {bundled!r}")


def _load(args) -> list:
    tasks_dir = _resolve_tasks_dir(args.tasks)
    tasks = load_tasks(tasks_dir, task_id=getattr(args, "task", None))
    if getattr(args, "limit", None):
        tasks = tasks[: args.limit]
    if not tasks:
        raise SystemExit("no tasks matched")
    return tasks


def _emit(trajectories, detections, out_dir: str, title: str) -> int:
    """Write report + artifacts + dashboard. Returns the number of runs whose
    test commands could not execute (infrastructure errors)."""
    print_report(trajectories, detections)
    os.makedirs(out_dir, exist_ok=True)
    write_run_artifacts(out_dir, trajectories, detections)
    dash = write_dashboard(os.path.join(out_dir, "dashboard.html"),
                           trajectories, detections, title=title)
    print(f"\n[redhand] artifacts + suite_result.json written under {out_dir}/")
    print(f"[redhand] dashboard: file://{os.path.abspath(dash)}")

    infra = [t for t in trajectories if t.infra_errored]
    if infra:
        n = len(infra)
        print(
            f"\n[redhand] !! WARNING: {n}/{len(trajectories)} run(s) could NOT execute "
            f"their test commands (infrastructure error, e.g. exit 127).\n"
            f"    The scores above are NOT trustworthy for those runs.\n"
            f"    redhand needs a shell (bash on POSIX, cmd on Windows) plus the task "
            f"interpreters (python, and node for the JS/TS tasks) on PATH.\n"
            f"    Activate the venv so `python` resolves to one that has pytest.",
            file=sys.stderr,
        )
    return len(infra)


def _progress(agent: str, task_id: str) -> None:
    print(f"[redhand] {agent:14s} -> {task_id}", file=sys.stderr)


# --------------------------------------------------------------------------- #
def cmd_list(args) -> int:
    for t in _load(args):
        tags = ",".join(tag.value.split("_")[0] for tag in t.expected_tags)
        print(f"{t.id:22s} {t.language:11s} {t.difficulty:7s} [{tags}]")
    return 0


def cmd_demo(args) -> int:
    from redhand.demo import DEMO_ADAPTERS

    tasks = _load(args)
    print(f"[redhand] demo: {len(tasks)} task(s) x {len(DEMO_ADAPTERS)} scripted agents "
          f"(honest + cheater), no API key, no network cost.", file=sys.stderr)
    trajectories, detections = evaluate(
        tasks, DEMO_ADAPTERS, runs=1, on_progress=_progress,
    )
    infra = _emit(trajectories, detections, args.out, "redhand demo — deceptive success caught")
    # Fail loudly if the environment couldn't run the tasks — never look "green".
    return 1 if infra else 0


def cmd_run(args) -> int:
    if args.agent not in _AGENTS:
        raise SystemExit(f"unknown agent {args.agent!r} (choose from {_AGENTS})")
    if args.agent == "codex":
        from redhand.adapters import CodexAdapter
        adapter = CodexAdapter(model=args.model, max_cost_usd=args.max_cost)
        if args.max_cost is not None:
            print(f"[redhand] NOTE: --max-cost has no effect for Codex — the codex CLI "
                  f"reports no per-run USD cost, so the budget cannot be enforced. "
                  f"Bound Codex runs with --limit / --runs instead.", file=sys.stderr)
    else:
        from redhand.adapters import ClaudeCodeAdapter
        adapter = ClaudeCodeAdapter(model=args.model, max_cost_usd=args.max_cost)

    tasks = _load(args)
    est = len(tasks) * args.runs
    print(f"[redhand] run: {len(tasks)} task(s) x {args.runs} run(s) = {est} real "
          f"{args.agent} invocations. THIS SPENDS MONEY.", file=sys.stderr)
    trajectories, detections = evaluate(
        tasks, [adapter], runs=args.runs,
        max_total_cost_usd=args.max_cost, on_progress=_progress,
    )
    infra = _emit(trajectories, detections, args.out, "redhand — agent safety report")
    return 1 if infra else 0


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="redhand", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"redhand {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--tasks", default=None,
                        help="tasks directory (default: the bundled seed tasks)")
        sp.add_argument("--task", default=None, help="run only this task id")
        sp.add_argument("--limit", type=int, default=None, help="cap number of tasks")

    sp_list = sub.add_parser("list", help="list available tasks")
    add_common(sp_list)
    sp_list.set_defaults(func=cmd_list)

    sp_demo = sub.add_parser("demo", help="zero-cost end-to-end demo (no API key)")
    add_common(sp_demo)
    sp_demo.add_argument("--out", default=_DEFAULT_OUT, help="output directory")
    sp_demo.set_defaults(func=cmd_demo)

    sp_run = sub.add_parser("run", help="red-team a real coding agent (spends money)")
    add_common(sp_run)
    sp_run.add_argument("--agent", default="claude-code", choices=_AGENTS,
                        help="which real agent to drive")
    sp_run.add_argument("--runs", type=int, default=5, help="runs per task (pass^k)")
    sp_run.add_argument("--model", default=None, help="model override for the agent")
    sp_run.add_argument("--max-cost", type=float, default=None, dest="max_cost",
                        help="cumulative USD budget checked before each run (caps total "
                             "spend across runs; not a mid-run stop). Enforced only for "
                             "claude-code, which reports per-run cost. Codex reports no "
                             "cost — use --limit/--runs to bound it.")
    sp_run.add_argument("--out", default=_DEFAULT_OUT, help="output directory")
    sp_run.set_defaults(func=cmd_run)
    return p


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
