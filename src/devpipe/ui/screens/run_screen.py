"""Run screen: timeline + logs + run metadata.

Compatible with Textual 8.x — uses render() and RichLog.
"""
from __future__ import annotations

from time import monotonic

from rich.text import Text

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import RichLog, Static

from devpipe.ui.state import StageAttempt, UIState
from devpipe.ui.widgets.status_bar import RunStatusBar

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def _format_duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


class RunStageStrip(Widget):
    """Top strip with completed and active stage attempts."""

    DEFAULT_CSS = """
    RunStageStrip {
        height: 5;
        padding: 1 2;
        background: $surface;
        border-bottom: solid $primary-darken-3;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._timeline: list[StageAttempt] = []
        self._spinner_frame = _SPINNER_FRAMES[0]

    def render(self) -> Text:
        visible_attempts = [attempt for attempt in self._timeline if attempt.status != "pending"]
        if not visible_attempts and self._timeline:
            visible_attempts = [self._timeline[0]]
        if not visible_attempts:
            return Text.from_markup("[dim]No active steps yet[/dim]")

        cards = []
        for attempt in visible_attempts:
            icon, style = self._icon_and_style(attempt)
            label = attempt.stage if attempt.attempt_number == 1 else f"{attempt.stage} #{attempt.attempt_number}"
            cards.append((f"{icon} {label}", _format_duration(attempt.elapsed_seconds), style))

        width = max(16, min(22, max(len(title) for title, _, _ in cards) + 3))
        top = Text()
        bottom = Text()
        for index, (title, duration, style) in enumerate(cards):
            if index:
                top.append("  ")
                bottom.append("  ")
            top.append(title[:width].ljust(width), style=style)
            bottom.append(duration[:width].ljust(width), style="dim")
        top.append("\n")
        top.append(bottom)
        return top

    def _icon_and_style(self, attempt: StageAttempt) -> tuple[str, str]:
        if attempt.status == "done":
            return "✓", "green"
        if attempt.status == "failed":
            return "✗", "red"
        return self._spinner_frame, "bold cyan"

    def set_timeline(self, timeline: list[StageAttempt]) -> None:
        self._timeline = timeline
        self.refresh()

    def set_spinner_frame(self, frame: str) -> None:
        self._spinner_frame = frame
        self.refresh()


class RunQuestionPanel(Widget):
    """Reserved area for questions and answer options."""

    DEFAULT_CSS = """
    RunQuestionPanel {
        width: 28;
        min-width: 24;
        background: $surface;
        border-right: solid $primary-darken-3;
        padding: 0;
    }
    RunQuestionPanel .question-title {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
    }
    RunQuestionPanel .question-body {
        padding: 1 2;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._body_markup = ""
        self.set_mode("idle")

    def compose(self) -> ComposeResult:
        yield Static("Question", classes="question-title")
        yield Static(self._body_markup, classes="question-body", id="question-body")

    def set_mode(self, mode: str) -> None:
        if mode == "confirm_cancel":
            self._body_markup = (
                "[dim]Stop pipeline and return to config?[/dim]\n\n"
                "[dim]Press Y to confirm or N to stay here.[/dim]"
            )
        elif mode == "cancelling":
            self._body_markup = "[dim]Cancelling pipeline...[/dim]"
        else:
            self._body_markup = (
                "[dim]No active question yet[/dim]\n\n"
                "[dim]Options will appear here when a stage asks for input.[/dim]"
            )
        try:
            self.query_one("#question-body", Static).update(Text.from_markup(self._body_markup))
        except Exception:
            pass


class RunLogOutput(RichLog):
    """RichLog that disables follow-tail while the operator scrolls away."""

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.parent.pause_follow()  # type: ignore[union-attr]
        super()._on_mouse_scroll_up(event)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        super()._on_mouse_scroll_down(event)
        if self.is_vertical_scroll_end:
            self.parent.resume_follow()  # type: ignore[union-attr]
        else:
            self.parent.pause_follow()  # type: ignore[union-attr]


class LogPanel(Widget, can_focus=True):
    """Log viewer using RichLog."""

    DEFAULT_CSS = """
    LogPanel {
        width: 1fr;
        background: $surface;
        padding: 0;
    }
    LogPanel .log-title {
        height: 1;
        padding: 0 2;
        color: $text-muted;
        background: $surface;
    }
    LogPanel RichLog {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._follow_tail: bool = True

    def compose(self) -> ComposeResult:
        yield Static("Output", classes="log-title")
        yield RunLogOutput(highlight=True, markup=False, wrap=True, id="log-output")

    def append(self, text: str) -> None:
        try:
            log = self.query_one("#log-output", RichLog)
            log.write(text, scroll_end=self._follow_tail, animate=False)
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

    def pause_follow(self) -> None:
        self._follow_tail = False

    def resume_follow(self) -> None:
        self._follow_tail = True

    def scroll_up(self) -> None:
        self.pause_follow()
        log = self.query_one("#log-output", RichLog)
        log.scroll_up(animate=False, immediate=True)

    def scroll_down(self) -> None:
        log = self.query_one("#log-output", RichLog)
        log.scroll_down(animate=False, immediate=True)
        if log.is_vertical_scroll_end:
            self.resume_follow()
        else:
            self.pause_follow()


class RunScreen(Screen):
    """Pipeline execution screen with timeline and logs."""

    BINDINGS = [
        Binding("up", "nav_up", "Up", show=False),
        Binding("down", "nav_down", "Down", show=False),
        Binding("escape", "back", "Back", show=True),
        Binding("y", "confirm_cancel", "Confirm Cancel", show=False),
        Binding("n", "dismiss_cancel", "Dismiss Cancel", show=False),
        Binding("f", "toggle_follow", "Follow Tail", show=True),
    ]

    DEFAULT_CSS = """
    RunScreen {
        layout: vertical;
    }
    RunScreen .run-body {
        height: 1fr;
    }
    RunScreen .run-main {
        height: 1fr;
    }
    """

    def __init__(self, ui_state: UIState, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state = ui_state
        self._run_started_at: float | None = None
        self._active_stage_started_at: float | None = None
        self._spinner_index = 0
        self._confirm_cancel = False
        self._cancelling = False

    def compose(self) -> ComposeResult:
        yield RunStageStrip(id="run-stage-strip")
        with Horizontal(classes="run-body"):
            yield RunQuestionPanel(id="run-question-panel")
            yield LogPanel(id="log-panel")
        yield RunStatusBar(id="run-status")

    def on_mount(self) -> None:
        if self._state.run_view.status == "running":
            self._run_started_at = monotonic()
        self.set_interval(0.2, self._tick_run_clock)
        self._update_run_display()

    def _update_run_display(self) -> None:
        rv = self._state.run_view
        stage_strip = self.query_one("#run-stage-strip", RunStageStrip)
        stage_strip.set_timeline(rv.timeline)
        stage_strip.set_spinner_frame(_SPINNER_FRAMES[self._spinner_index % len(_SPINNER_FRAMES)])
        question = self.query_one("#run-question-panel", RunQuestionPanel)
        question.set_mode("idle")

        status = self.query_one("#run-status", RunStatusBar)
        status.update_run_state(
            status=rv.status,
            elapsed=_format_duration(rv.elapsed_seconds),
            model=rv.model_name,
            effort=rv.effort,
        )
        if self._cancelling:
            status.show_alert("Cancelling pipeline...")
        elif self._confirm_cancel:
            status.show_alert("Stop pipeline? Y — confirm  N — stay")
        else:
            status.clear_alert()

    def _tick_run_clock(self) -> None:
        if self._state.run_view.status != "running":
            return
        now = monotonic()
        if self._run_started_at is not None:
            self._state.run_view.elapsed_seconds = now - self._run_started_at
        if self._active_stage_started_at is not None:
            for attempt in self._state.run_view.timeline:
                if attempt.status == "active":
                    attempt.elapsed_seconds = now - self._active_stage_started_at
                    break
        self._spinner_index += 1
        self._update_run_display()

    # ── Run event handlers (called from app) ──────────────────────────────

    def on_stage_started(self, stage: str, runner: str, model: str, effort: str) -> None:
        if any(attempt.stage == stage and attempt.status == "active" for attempt in self._state.run_view.timeline):
            self._state.run_view.runner_name = runner
            self._state.run_view.model_name = model
            self._state.run_view.effort = effort
            self._update_run_display()
            return

        now = monotonic()
        if self._run_started_at is None:
            self._run_started_at = now
        self._active_stage_started_at = now
        self._state.run_view.active_stage = stage
        self._state.run_view.runner_name = runner
        self._state.run_view.model_name = model
        self._state.run_view.effort = effort

        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n▶ Started: {stage}\n")

    def on_stage_completed(self, stage: str, summary: str = "") -> None:
        now = monotonic()
        for attempt in self._state.run_view.timeline:
            if attempt.stage == stage and attempt.status == "active":
                attempt.status = "done"
                attempt.summary = summary
                if self._active_stage_started_at is not None:
                    attempt.elapsed_seconds = now - self._active_stage_started_at
                break
        self._active_stage_started_at = None
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n✓ Completed: {stage}\n")

    def on_stage_failed(self, stage: str, error: str = "") -> None:
        now = monotonic()
        for attempt in self._state.run_view.timeline:
            if attempt.stage == stage and attempt.status == "active":
                attempt.status = "failed"
                attempt.error = error
                if self._active_stage_started_at is not None:
                    attempt.elapsed_seconds = now - self._active_stage_started_at
                break
        self._active_stage_started_at = None
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(f"\n✗ Failed: {stage}\n{error}\n" if error else f"\n✗ Failed: {stage}\n")

    def on_output(self, text: str) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.append(text)

    def on_run_finished(self, status: str, run_id: str) -> None:
        now = monotonic()
        self._confirm_cancel = False
        self._cancelling = False
        self._state.run_view.status = status
        self._state.run_view.run_id = run_id
        if self._run_started_at is not None:
            self._state.run_view.elapsed_seconds = now - self._run_started_at
        self._active_stage_started_at = None
        self._update_run_display()
        log_panel = self.query_one("#log-panel", LogPanel)
        if status == "completed":
            log_panel.append(f"\n✓ Pipeline completed  {run_id}\n")
        elif status == "cancelled":
            log_panel.append(f"\n■ Pipeline cancelled  {run_id}\n")
        else:
            log_panel.append(f"\n✗ Pipeline failed  {run_id}\n")

    # ── Navigation ────────────────────────────────────────────────────────

    def action_nav_up(self) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.scroll_up()

    def action_nav_down(self) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.scroll_down()

    def action_back(self) -> None:
        if self._state.run_view.status == "running":
            if self._cancelling:
                return
            self._confirm_cancel = not self._confirm_cancel
            self._update_run_display()
            return
        self.app.pop_screen()

    def action_confirm_cancel(self) -> None:
        if not self._confirm_cancel or self._cancelling:
            return
        self._confirm_cancel = False
        self._cancelling = True
        self._update_run_display()
        self._begin_cancel_return()

    def action_dismiss_cancel(self) -> None:
        if not self._confirm_cancel or self._cancelling:
            return
        self._confirm_cancel = False
        self._update_run_display()

    def action_toggle_follow(self) -> None:
        log_panel = self.query_one("#log-panel", LogPanel)
        log_panel.toggle_follow()

    def _finish_cancel_return(self) -> None:
        self._confirm_cancel = False
        self._cancelling = False
        self.app.pop_screen()

    def _begin_cancel_return(self) -> None:
        self.app.cancel_active_run_async(self._finish_cancel_return)
