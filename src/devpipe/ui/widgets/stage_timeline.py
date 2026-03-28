"""Timeline widget for the run screen.

Uses render() for Textual 8.x compatibility.
"""
from __future__ import annotations

from rich.text import Text

from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget

from devpipe.ui.state import StageAttempt


_STATUS_ICONS = {
    "pending": "○",
    "active": "◉",
    "done": "✓",
    "failed": "✗",
    "skipped": "–",
}

_STATUS_STYLES = {
    "pending": "dim",
    "active": "bold cyan",
    "done": "green",
    "failed": "red",
    "skipped": "dim",
}


class StageTimeline(Widget, can_focus=True):
    """Vertical timeline of stage attempts."""

    DEFAULT_CSS = """
    StageTimeline {
        width: 1fr;
        min-width: 28;
        max-width: 40;
        background: $surface;
        border-right: solid $primary-darken-3;
        padding: 1 0;
    }
    """

    selected_index: reactive[int] = reactive(0)

    class StageSelected(Message):
        def __init__(self, attempt: StageAttempt, index: int) -> None:
            super().__init__()
            self.attempt = attempt
            self.index = index

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._timeline: list[StageAttempt] = []

    def render(self) -> Text:
        text = Text()
        text.append("╸ Timeline\n", style="bold dim")

        for i, attempt in enumerate(self._timeline):
            icon = _STATUS_ICONS.get(attempt.status, "?")
            style = _STATUS_STYLES.get(attempt.status, "")
            label = f"  {icon} {attempt.stage} #{attempt.attempt_number}"
            if i == self.selected_index:
                style = "reverse " + style
            text.append(f"{label}\n", style=style)

        if not self._timeline:
            text.append("  (no stages)\n", style="dim")

        return text

    def set_timeline(self, timeline: list[StageAttempt]) -> None:
        """Update timeline and re-render."""
        self._timeline = timeline
        self.refresh()

    def watch_selected_index(self, new_value: int) -> None:
        self.refresh()

    def move_up(self) -> None:
        if self.selected_index > 0:
            self.selected_index -= 1
            if self._timeline:
                self.post_message(self.StageSelected(self._timeline[self.selected_index], self.selected_index))

    def move_down(self) -> None:
        if self.selected_index < len(self._timeline) - 1:
            self.selected_index += 1
            if self._timeline:
                self.post_message(self.StageSelected(self._timeline[self.selected_index], self.selected_index))
