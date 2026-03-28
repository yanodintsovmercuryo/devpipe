"""Log viewer widget with follow-tail mode."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog


class LogViewer(Widget):
    """Append-only log viewer with scroll support and follow-tail."""

    DEFAULT_CSS = """
    LogViewer {
        width: 2fr;
        background: $surface;
        padding: 0;
    }
    LogViewer RichLog {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._follow_tail: bool = True

    def compose(self) -> ComposeResult:
        yield RichLog(
            highlight=True,
            markup=False,
            wrap=True,
            id="log-output",
        )

    def append(self, text: str) -> None:
        """Append text to the log."""
        log = self.query_one("#log-output", RichLog)
        log.write(text)
        if self._follow_tail:
            log.scroll_end(animate=False)

    def clear(self) -> None:
        """Clear all log content."""
        log = self.query_one("#log-output", RichLog)
        log.clear()

    def toggle_follow(self) -> None:
        """Toggle follow-tail mode."""
        self._follow_tail = not self._follow_tail
