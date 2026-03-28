"""Run screen: timeline + logs + run metadata.

Compatible with Textual 8.x — uses render() and RichLog.
"""
from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import RichLog

from devpipe.ui.state import RunViewState, StageAttempt, UIState
from devpipe.ui.widgets.stage_timeline import StageTimeline
from devpipe.ui.widgets.status_bar import RunStatusBar


class RunMeta(Widget):
    """Run metadata header."""

    DEFAULT_CSS = """
    RunMeta {
        height: 3;
        padding: 0 2;
        background: $surface;
        border-bottom: solid $primary-darken-3;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = ""
        self._info = ""

    def render(self) -> Text:
        text = Text()
        text.append(f"{self._title}\n", style="bold cyan")
        text.append(self._info, style="dim")
        return text

    def update_meta(self, title: str, info: str) -> None:
        self._title = title
        self._info = info
        self.refresh()


class LogPanel(Widget, can_focus=True):
    """Log viewer using RichLog."""

    DEFAULT_CSS = """
    LogPanel {
        width: 2fr;
        background: $surface;
        padding: 0;
    }
    LogPanel RichLog {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._follow_tail: bool = True

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=False, wrap=True, id="log-output")

    def append(self, text: str) -> None:
        try:
            log = self.query_one("#log-output", RichLog)
            log.write(text)
            if self._follow_tail:
                log.scroll_end(animate=False)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            log = self.query_one("#log-output", RichLog)
            log.clear()
        except Exception:
            pass

    def toggle_follow(self) -> None:
        self._follow_tail = not self._follow_tail


class RunScreen(Screen):
    """Pipeline execution screen with timeline and logs."""

    BINDINGS = [
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("escape", "back", "Back", show=True),
        Binding("f", "toggle_follow", "Follow Tail", show=True),
    ]

    DEFAULT_CSS = """
    RunScreen {
        layout: vertical;
    }
    RunScreen .run-main {
        height: 1fr;
    }
    """

    def __init__(self, ui_state: UIState, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = ui_state

    def compose(self) -> ComposeResult:
        yield RunMeta(id="run-meta")
        with Horizontal(classes="run-main"):
            yield StageTimeline(id="timeline")
            yield LogPanel(id="log-panel")
        yield RunStatusBar(id="run-status")

    def on_mount(self) -> None:
        self._update_run_display()

    def _update_run_display(self) -> None:
        rv = self._state.run_view
        meta = self.query_one("#run-meta", RunMeta)
        info_parts = [f"status: {rv.status}"]
        if rv.runner_name:
            info_parts.append(f"runner: {rv.runner_name}")
        if rv.model_name:
            info_parts.append(f"model: {rv.model_name}")
        meta.update_meta(f"╸ Run {rv.run_id}", "  ".join(info_parts))

        timeline = self.query_one("#timeline", StageTimeline)
        timeline.set_timeline(rv.timeline)

        status = self.query_one("#run-status", RunStatusBar)
        status.update_run_state(
            stage=rv.active_stage,
            status=rv.status,
            runner=rv.runner_name,
            model=rv.model_name,
        )

    # ── Run event handlers (called from app) ──────────────────────────────

    def on_stage_started(self, stage: str, runner: str, model: str, effort: str) -> None:
        self._state.run_view.active_stage = stage
        self._state.run_view.runner_name = runner
        self._state.run_view.model_name = model
        self._state.run_view.effort = effort

        for attempt in self._state.run_view.timeline:
            if attempt.stage == stage and attempt.status == "pending":
                attempt.status = "active"
                break
        else:
            existing = [a for a in self._state.run_view.timeline if a.stage == stage]
            self._state.run_view.timeline.append(
                StageAttempt(stage=stage, attempt_number=len(existing) + 1, status="active")
            )

        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n── {stage} ──\n")

    def on_stage_completed(self, stage: str, summary: str = "") -> None:
        for attempt in self._state.run_view.timeline:
            if attempt.stage == stage and attempt.status == "active":
                attempt.status = "done"
                attempt.summary = summary
                break
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n✓ {stage} completed\n")

    def on_stage_failed(self, stage: str, error: str = "") -> None:
        for attempt in self._state.run_view.timeline:
            if attempt.stage == stage and attempt.status == "active":
                attempt.status = "failed"
                attempt.error = error
                break
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n✗ {stage} failed: {error}\n")

    def on_output(self, text: str) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(text)

    def on_run_finished(self, status: str, run_id: str) -> None:
        self._state.run_view.status = status
        self._state.run_view.run_id = run_id
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        if status == "completed":
            log_panel.append(f"\n✓ Pipeline completed  {run_id}\n")
        else:
            log_panel.append(f"\n✗ Pipeline failed  {run_id}\n")

    # ── Navigation ────────────────────────────────────────────────────────

    def action_nav_up(self) -> None:
        timeline = self.query_one("#timeline", StageTimeline)
        timeline.move_up()

    def action_nav_down(self) -> None:
        timeline = self.query_one("#timeline", StageTimeline)
        timeline.move_down()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_toggle_follow(self) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.toggle_follow()
