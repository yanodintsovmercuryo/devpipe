"""History entry preview widget.

Uses render() for Textual 8.x compatibility.
"""
from __future__ import annotations

from rich.text import Text

from textual.widget import Widget

from devpipe.ui.widgets.task_snapshot import (
    build_task_snapshot_lines,
    compact_history_title,
    custom_fields_from_history_entry,
)


class HistoryPreview(Widget):
    """Preview panel for a history entry."""

    DEFAULT_CSS = """
    HistoryPreview {
        width: 2fr;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._markup: str = "[dim]Select an entry[/dim]"

    def render(self) -> Text:
        return Text.from_markup(self._markup)

    def show_entry(self, entry: dict) -> None:
        """Render a history entry preview."""
        snapshot_values = {
            "task": entry.get("task", ""),
            "runner": entry.get("runner", ""),
            "model": entry.get("model", ""),
            "effort": entry.get("effort", ""),
            "tags": entry.get("tags", []),
            "first_role": entry.get("first_role", ""),
            "last_role": entry.get("last_role", ""),
            "task_id": entry.get("task_id", ""),
            "target_branch": entry.get("target_branch", ""),
            "service": entry.get("service", ""),
            "namespace": entry.get("namespace", ""),
        }
        extra = entry.get("extra_params", {})
        if isinstance(extra, dict):
            snapshot_values.update(extra)

        lines = [f"[bold cyan]╸ {compact_history_title(entry.get('task', ''))}[/bold cyan]\n"]
        lines.extend(build_task_snapshot_lines(snapshot_values, custom_fields_from_history_entry(entry)))

        self._markup = "\n".join(lines)
        self.refresh()

    def clear(self) -> None:
        self._markup = "[dim]Select an entry[/dim]"
        self.refresh()
