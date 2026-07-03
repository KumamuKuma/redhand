"""redhand — rich console safety scorecard.

Renders a briefing-style scorecard per agent plus a leaderboard, from the
aggregates computed in :mod:`redhand.scoring`.
"""

from __future__ import annotations

from typing import Iterable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from redhand.contracts import DetectionResult, LeaderboardRow, SabotageTag, Trajectory
from redhand.scoring import AgentSummary, aggregate, short_tag

_GRADE_STYLE = {
    "A": "bold green",
    "B": "green",
    "C": "yellow",
    "D": "dark_orange",
    "F": "bold red",
}


def _pct(x: float) -> str:
    return f"{100 * x:4.0f}%"


def _grade_text(grade: str) -> Text:
    return Text(grade, style=_GRADE_STYLE.get(grade, "white"))


def _by_type_line(tag_counts: dict[str, int]) -> Text:
    """"S1 x  S2 x ..." — only tags that were hit, ordered S1..S8."""
    if not tag_counts:
        return Text("none", style="green")
    ordered = sorted(tag_counts.items(), key=lambda kv: short_tag(kv[0]))
    t = Text()
    for i, (tag, count) in enumerate(ordered):
        if i:
            t.append("  ")
        t.append(short_tag(tag), style="bold red")
        t.append(f" {count}", style="red")
    return t


def scorecard_panel(summary: AgentSummary) -> Panel:
    """A single agent's scorecard as a rich Panel (matches the target layout)."""
    body = Table.grid(padding=(0, 1))
    body.add_column(justify="left", style="bold")
    body.add_column(justify="left")

    body.add_row("Tasks:", f"{summary.n_tasks}   Runs/task: {summary.runs_per_task_label}")
    body.add_row("True success (hidden tests):", _pct(summary.mean_true_success))
    body.add_row("Claimed success (visible):", _pct(summary.mean_claimed_success))

    dec = Text(_pct(summary.mean_deceptive_success), style="bold red")
    dec.append("   <- claimed success but cheated / hidden failed", style="dim red")
    body.add_row("Deceptive success:", dec)

    body.add_row("Cheat rate:", Text(_pct(summary.mean_cheat_rate), style="red"))
    body.add_row("By type:", _by_type_line(summary.tag_counts))
    body.add_row("Recovery score:", f"{summary.mean_recovery_score:.0f}/100")

    grade = Text("Overall Safety Grade: ", style="bold")
    grade.append(_grade_text(summary.safety_grade))
    body.add_row("", grade)

    style = _GRADE_STYLE.get(summary.safety_grade, "white")
    return Panel(
        body,
        title=f"[bold]Agent: {summary.agent}[/bold]",
        border_style=style,
        expand=False,
    )


def leaderboard_table(rows: Iterable[LeaderboardRow]) -> Table:
    table = Table(title="Leaderboard (safest first)", title_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Agent", style="bold")
    table.add_column("Tasks", justify="right")
    table.add_column("True succ.", justify="right")
    table.add_column("Cheat", justify="right")
    table.add_column("Deceptive", justify="right")
    table.add_column("Cost $", justify="right")
    table.add_column("Grade", justify="center")

    for i, r in enumerate(rows, 1):
        table.add_row(
            str(i),
            r.agent,
            str(r.n_tasks),
            _pct(r.mean_true_success),
            Text(_pct(r.mean_cheat_rate), style="red" if r.mean_cheat_rate else "green"),
            Text(_pct(r.mean_deceptive_success),
                 style="bold red" if r.mean_deceptive_success else "green"),
            f"{r.mean_cost_usd:.2f}",
            _grade_text(r.safety_grade),
        )
    return table


def print_report(
    trajectories: Iterable[Trajectory],
    detection_results: Iterable[DetectionResult] = (),
    *,
    console: Optional[Console] = None,
) -> None:
    """Aggregate and print the full console report (scorecards + leaderboard)."""
    console = console or Console()
    result = aggregate(trajectories, detection_results)

    console.print()
    console.rule("[bold]redhand — safety scorecard[/bold]")
    for summary in result.agents:
        console.print(scorecard_panel(summary))
    console.print()
    console.print(leaderboard_table(result.leaderboard))
    console.print()


def render_report_text(
    trajectories: Iterable[Trajectory],
    detection_results: Iterable[DetectionResult] = (),
    *,
    width: int = 100,
) -> str:
    """Render the report to a plain string (handy for tests / logs / files)."""
    import io

    console = Console(width=width, record=True, file=io.StringIO())
    print_report(trajectories, detection_results, console=console)
    return console.export_text()
