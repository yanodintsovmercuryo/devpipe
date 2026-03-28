"""History screen: list of past runs with preview and restore.

Compatible with Textual 8.x.
"""
from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widget import Widget

from devpipe.history import load_history
from devpipe.ui.state import UIState
from devpipe.ui.widgets.history_preview import HistoryPreview


class HistoryList(Widget, can_focus=True):
    """Vertical list of history entries."""

    DEFAULT_CSS = """
    HistoryList {
        width: 1fr;
        min-width: 28;
        max-width: 40;
        background: $surface;
        border-right: solid $primary-darken-3;
        padding: 1 0;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: list[dict] = []
        self._selected: int = 0

    def render(self) -> Text:
        text = Text()
        text.append("╸ History\n\n", style="bold dim")
        for i, entry in enumerate(self._entries):
            date = entry.get("date", "")
            task = (entry.get("task", "") or "")[:40]
            if i == self._selected:
                text.append(f"  » {date}  {task}\n", style="bold cyan")
            else:
                text.append(f"    {date}  {task}\n", style="dim")
        if not self._entries:
            text.append("  No history entries\n", style="dim")
        return text

    def set_entries(self, entries: list[dict]) -> None:
        self._entries = entries
        self._selected = 0
        self.refresh()

    def move_up(self) -> None:
        if self._selected > 0:
            self._selected -= 1
            self.refresh()

    def move_down(self) -> None:
        if self._selected < len(self._entries) - 1:
            self._selected += 1
            self.refresh()

    @property
    def current_entry(self) -> dict | None:
        if self._entries and 0 <= self._selected < len(self._entries):
            return self._entries[self._selected]
        return None


class HistoryStatusBar(Widget):
    """Status bar for history screen."""

    DEFAULT_CSS = """
    HistoryStatusBar {
        height: 1;
        dock: bottom;
        background: $primary-darken-3;
        color: $text;
    }
    """

    def render(self) -> Text:
        return Text.from_markup(" [dim]Enter — restore  ·  Esc — back[/dim]")


class HistoryScreen(Screen):
    """Screen showing history entries with preview and restore."""

    BINDINGS = [
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("enter", "restore", "Restore", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    DEFAULT_CSS = """
    HistoryScreen {
        layout: vertical;
    }
    HistoryScreen .history-main {
        height: 1fr;
    }
    """

    class RestoreEntry(Message):
        """Request to restore a history entry into form."""
        def __init__(self, entry: dict) -> None:
            super().__init__()
            self.entry = entry

    def __init__(self, ui_state: UIState, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = ui_state

    def compose(self) -> ComposeResult:
        with Horizontal(classes="history-main"):
            yield HistoryList(id="history-list")
            yield HistoryPreview(id="history-preview")
        yield HistoryStatusBar()

    def on_mount(self) -> None:
        entries = load_history()[:20]
        hist_list = self.query_one("#history-list", HistoryList)
        hist_list.set_entries(entries)
        if entries:
            preview = self.query_one("#history-preview", HistoryPreview)
            preview.show_entry(entries[0])

    def action_nav_up(self) -> None:
        hist_list = self.query_one("#history-list", HistoryList)
        hist_list.move_up()
        self._show_preview()

    def action_nav_down(self) -> None:
        hist_list = self.query_one("#history-list", HistoryList)
        hist_list.move_down()
        self._show_preview()

    def _show_preview(self) -> None:
        hist_list = self.query_one("#history-list", HistoryList)
        entry = hist_list.current_entry
        if entry:
            preview = self.query_one("#history-preview", HistoryPreview)
            preview.show_entry(entry)

    def action_restore(self) -> None:
        hist_list = self.query_one("#history-list", HistoryList)
        entry = hist_list.current_entry
        if entry:
            self.post_message(self.RestoreEntry(entry))
            self.app.pop_screen()

    def action_back(self) -> None:
        self.app.pop_screen()
