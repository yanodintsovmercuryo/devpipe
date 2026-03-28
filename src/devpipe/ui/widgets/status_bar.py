"""Bottom status bar widgets.

Uses render() for Textual 8.x compatibility.
"""
from __future__ import annotations

from rich.text import Text

from textual.widget import Widget

from devpipe.ui.state import StatusBarState


class StatusBar(Widget):
    """Bottom status bar: shortcuts, help, readiness."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $primary-darken-3;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._left = ""
        self._center = ""
        self._right = ""
        self._is_ready = False

    def render(self) -> Text:
        text = Text()
        text.append(f" {self._left}", style="dim")
        text.append("  ")
        text.append(self._center, style="dim")
        text.append("  ")
        style = "bold green" if self._is_ready else "bold yellow"
        text.append(self._right, style=style)
        return text

    def update_state(self, state: StatusBarState) -> None:
        """Update the status bar from state."""
        self._left = state.left_text
        self._center = state.center_text
        self._right = state.right_text
        self._is_ready = state.is_ready
        self.refresh()


class RunStatusBar(Widget):
    """Bottom status bar for run mode."""

    DEFAULT_CSS = """
    RunStatusBar {
        height: 1;
        dock: bottom;
        background: $primary-darken-3;
        color: $text;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._stage = ""
        self._status = ""
        self._runner = ""
        self._model = ""
        self._elapsed = ""

    def render(self) -> Text:
        text = Text()
        text.append(" Esc — back", style="dim")
        text.append("  ")
        center = self._stage
        if self._status:
            center += f" · {self._status}"
        text.append(center)
        text.append("  ")
        right_parts = []
        if self._runner:
            right_parts.append(f"runner {self._runner}")
        if self._model:
            right_parts.append(f"model {self._model}")
        if self._elapsed:
            right_parts.append(self._elapsed)
        text.append("  ".join(right_parts), style="dim")
        return text

    def update_run_state(
        self,
        stage: str = "",
        status: str = "",
        elapsed: str = "",
        runner: str = "",
        model: str = "",
    ) -> None:
        self._stage = stage
        self._status = status
        self._elapsed = elapsed
        self._runner = runner
        self._model = model
        self.refresh()
