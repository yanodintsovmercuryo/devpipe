"""History entry preview widget.

Uses render() for Textual 8.x compatibility.
"""
from __future__ import annotations

from rich.text import Text

from textual.widget import Widget


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
        date = entry.get("date", "")
        task = entry.get("task", "(empty)")

        lines = [f"[bold cyan]╸ {date}[/bold cyan]\n"]

        rows = [
            ("task", task),
            ("task-id", entry.get("task_id", "—")),
            ("runner", entry.get("runner", "")),
            ("target-branch", entry.get("target_branch", "") or "none"),
            ("service", entry.get("service", "")),
            ("namespace", entry.get("namespace", "") or "auto"),
            ("tags", ", ".join(entry.get("tags", [])) or "none"),
        ]

        extra = entry.get("extra_params", {})
        for k, v in extra.items():
            display = ", ".join(v) if isinstance(v, list) else str(v)
            rows.append((f"  {k}", display))

        first = entry.get("first_role", "") or "architect"
        last = entry.get("last_role", "") or "qa_stand"
        rows.append(("roles", f"{first} → {last}"))

        key_w = max(len(r[0]) for r in rows) + 2
        for key, val in rows:
            lines.append(f"  [dim]{key.ljust(key_w)}[/dim] {val}")

        self._markup = "\n".join(lines)
        self.refresh()

    def clear(self) -> None:
        self._markup = "[dim]Select an entry[/dim]"
        self.refresh()
