"""redhand.reporting — turn scored results into human output.

Two sinks, both driven by :mod:`redhand.scoring`:

* :mod:`redhand.reporting.console` — a rich terminal safety scorecard.
* :mod:`redhand.reporting.html` — a static, fully-offline HTML dashboard.
"""

from __future__ import annotations

from redhand.reporting.console import (  # noqa: F401
    leaderboard_table,
    print_report,
    render_report_text,
    scorecard_panel,
)
from redhand.reporting.html import (  # noqa: F401
    render_dashboard,
    write_dashboard,
)

__all__ = [
    "print_report",
    "render_report_text",
    "scorecard_panel",
    "leaderboard_table",
    "render_dashboard",
    "write_dashboard",
]
