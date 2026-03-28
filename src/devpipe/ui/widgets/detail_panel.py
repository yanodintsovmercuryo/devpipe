"""Right-side detail/summary panel with inline editing support."""
from __future__ import annotations

from typing import Any

from rich.text import Text

from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from devpipe.ui.state import FieldKind, FieldMeta, FormState, NavItem, NavSection


class DetailPanel(Widget):
    """Right panel: summary/inline-edit for the currently selected nav item."""

    DEFAULT_CSS = """
    DetailPanel {
        width: 2fr;
        layout: vertical;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    DetailPanel .editor-copy {
        width: 1fr;
        height: auto;
    }
    DetailPanel .editor-copy--top {
        margin-bottom: 1;
    }
    DetailPanel .editor-copy--bottom {
        margin-top: 1;
    }
    DetailPanel #inline-input {
        width: 1fr;
        margin: 0;
        border: none;
        padding: 0 1;
        background: $panel;
        color: $text;
    }
    DetailPanel #inline-input:focus {
        border: tall #6b7280;
    }
    """

    class FieldValueChanged(Message):
        """Emitted when user changes a field value via inline edit."""
        def __init__(self, key: str, value: Any) -> None:
            super().__init__()
            self.key = key
            self.value = value

    class ActionRequested(Message):
        """Emitted when user activates a nav action (History, Run)."""
        def __init__(self, action: str) -> None:
            super().__init__()
            self.action = action

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_item: NavItem | None = None
        self._form: FormState = FormState()
        self._editing: bool = False
        self._edit_field: str = ""
        self._summary_text: str = "Select an item"
        self._editor_mode: str = "none"
        self._editor_options: list[str] = []
        self._editor_selected_index: int = 0
        self._editor_selected_values: list[str] = []
        self._editor_committed_value: Any = ""
        self._editor_allows_custom: bool = False
        self._editor_custom_prompt: bool = False

    def render(self) -> Text:
        """Render the detail panel as Rich Text."""
        return Text.from_markup(self._summary_text)

    def show_summary(self, item: NavItem, form: FormState) -> None:
        """Display current values for the selected nav item."""
        self._current_item = item
        self._form = form
        self._editing = False
        self._editor_mode = "none"
        self._editor_options = []
        self._editor_selected_index = 0
        self._editor_selected_values = []
        self._editor_committed_value = ""
        self._editor_allows_custom = False
        self._editor_custom_prompt = False

        # Remove any mounted edit widgets
        for child in list(self.children):
            child.remove()

        lines: list[str] = [f"[bold cyan]╸ {item.label}[/bold cyan]\n"]

        if item.is_action:
            if item.key == "run":
                missing = form.missing_required()
                if missing:
                    lines.append(f"[bold red]Cannot run:[/bold red] Missing: {', '.join(missing)}")
                else:
                    lines.append("[bold green]Ready to run pipeline[/bold green]")
                    lines.append("\n[dim]Press Enter to start the pipeline[/dim]")
            elif item.key == "history":
                lines.append("[dim]Press Enter to open history[/dim]")
            self._summary_text = "\n".join(lines)
            self.refresh()
            return

        value = form.values.get(item.key, "")
        field_meta = form.field_by_key(item.key)

        self._add_standard_summary(lines, form, item.key)
        self._add_field_detail(lines, item.key, value, field_meta, form)

        lines.append("\n[dim]Enter — edit  ·  Esc — back[/dim]")
        self._summary_text = "\n".join(lines)
        self.refresh()

    def _add_standard_summary(self, lines: list[str], form: FormState, highlight_key: str) -> None:
        """Add summary of standard fields to lines."""
        standard = [
            ("profile", "Profile"),
            ("task", "Task"),
            ("runner", "Runner"),
            ("model", "Model"),
            ("effort", "Effort"),
            ("tags", "Tags"),
            ("first_role", "Start Stage"),
            ("last_role", "Finish Stage"),
        ]
        for key, label in standard:
            val = form.values.get(key, "")
            display_val = str(val) if val else "[dim](empty)[/dim]"
            if key == highlight_key:
                lines.append(f" [bold]▸ {label}:[/bold] {display_val}")
            else:
                lines.append(f"   {label}: {display_val}")

        # Custom fields summary
        has_custom = False
        for f in form.fields:
            if f.section == "custom":
                if not has_custom:
                    lines.append("\n[dim]── Custom ──[/dim]")
                    has_custom = True
                val = form.values.get(f.key, "")
                display_val = self._format_value(val)
                if f.key == highlight_key:
                    lines.append(f" [bold]▸ {f.label}:[/bold] {display_val}")
                else:
                    lines.append(f"   {f.label}: {display_val}")

    def _add_field_detail(self, lines: list[str], key: str, value: Any, field_meta: FieldMeta | None, form: FormState) -> None:
        """Add detail view for a custom field."""
        display_val = self._format_value(value)
        lines.append("")
        lines.append(f"  Current: {display_val}")

        if field_meta:
            if field_meta.description:
                lines.append(f"\n  [dim]{field_meta.description}[/dim]")
            if field_meta.required:
                lines.append("  [yellow]Required[/yellow]")
            return

        description, _type_name, _options = self._standard_field_details(key, form)
        if description:
            lines.append(f"\n  [dim]{description}[/dim]")

    def _standard_field_details(self, key: str, form: FormState) -> tuple[str, str, list[str]]:
        if key == "profile":
            return ("Active project profile", "select", list(form.available_profiles))
        if key == "runner":
            return ("Runner selection mode", "select", list(form.available_runners))
        if key == "model":
            return ("Model level override for all stages", "select", list(form.available_models))
        if key == "effort":
            return ("Reasoning effort override for all stages", "select", list(form.available_efforts))
        if key == "tags":
            field_meta = form.field_by_key("tags")
            return ("Pipeline tags", "multi_select", list(field_meta.options) if field_meta else [])
        if key == "first_role":
            return ("First enabled stage in the pipeline", "select", self._bounded_stage_options(form, key))
        if key == "last_role":
            return ("Last enabled stage in the pipeline", "select", self._bounded_stage_options(form, key))
        return ("Task text passed to the pipeline", "text", [])

    @staticmethod
    def _bounded_stage_options(form: FormState, key: str) -> list[str]:
        stages = list(form.available_stages)
        if not stages:
            return []
        first = form.values.get("first_role")
        last = form.values.get("last_role")
        if key == "first_role" and last in stages:
            return stages[: stages.index(last) + 1]
        if key == "last_role" and first in stages:
            return stages[stages.index(first):]
        return stages

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None or value == "":
            return "[dim](empty)[/dim]"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value) if value else "[dim](empty)[/dim]"
        if isinstance(value, dict):
            if not value:
                return "[dim](empty)[/dim]"
            parts = [f"{k}={v}" for k, v in value.items()]
            return ", ".join(parts)
        return str(value)

    def begin_edit(self, item: NavItem, form: FormState) -> None:
        """Switch to inline-edit mode for the current field."""
        if item.is_action:
            self.post_message(self.ActionRequested(item.key))
            return

        self._editing = True
        self._current_item = item
        self._edit_field = item.key
        self._form = form
        self._editor_mode = "none"
        self._editor_options = []
        self._editor_selected_index = 0
        self._editor_selected_values = []
        self._editor_committed_value = ""
        self._editor_allows_custom = False
        self._editor_custom_prompt = False

        # Remove any children first
        for child in list(self.children):
            child.remove()

        value = form.values.get(item.key, "")
        field_meta = form.field_by_key(item.key)
        kind = field_meta.kind if field_meta else FieldKind.STRING

        if item.key == "profile":
            self._setup_single_choice_editor(item.label, value, form.available_profiles)
        elif item.key == "runner":
            self._setup_single_choice_editor(item.label, value, form.available_runners)
        elif item.key == "model":
            self._setup_single_choice_editor(item.label, value, form.available_models)
        elif item.key == "effort":
            self._setup_single_choice_editor(item.label, value, form.available_efforts)
        elif item.key in ("first_role", "last_role"):
            self._setup_single_choice_editor(item.label, value, self._bounded_stage_options(form, item.key))
        elif item.key == "namespace" and field_meta:
            self._setup_single_choice_editor(item.label, value, field_meta.options, allow_custom=True)
        elif item.key == "tags" and field_meta:
            self._setup_multi_choice_editor(item.label, value, field_meta.options, allow_custom=True)
        elif kind == FieldKind.SELECT and field_meta and field_meta.options:
            self._setup_single_choice_editor(item.label, value, field_meta.options)
        elif kind == FieldKind.MULTI_SELECT and field_meta and field_meta.options:
            self._setup_multi_choice_editor(item.label, value, field_meta.options)
        elif kind == FieldKind.ARRAY:
            self._mount_text_editor(item.key, ", ".join(value) if isinstance(value, list) else str(value))
        elif kind == FieldKind.OBJECT:
            if isinstance(value, dict):
                text = ", ".join(f"{k}={v}" for k, v in value.items())
            else:
                text = str(value) if value else ""
            self._mount_text_editor(item.key, text)
        else:
            self._mount_text_editor(item.key, str(value) if value else "")

        self.refresh()

    def _setup_single_choice_editor(self, label: str, current: Any, options: list[str], allow_custom: bool = False) -> None:
        self._editing = True
        self._editor_mode = "single_choice"
        self._editor_allows_custom = allow_custom
        self._editor_options = self._normalize_options(options, current)
        self._editor_selected_index = self._editor_options.index(str(current)) if str(current) in self._editor_options else 0
        self._editor_committed_value = str(current) if current not in (None, "") else ""
        self._summary_text = self._render_choice_editor(label, multi=False)

    def _setup_multi_choice_editor(self, label: str, current: Any, options: list[str], allow_custom: bool = False) -> None:
        self._editing = True
        self._editor_mode = "multi_choice"
        self._editor_allows_custom = allow_custom
        current_values = [str(v) for v in current] if isinstance(current, list) else ([str(current)] if current else [])
        self._editor_selected_values = current_values
        self._editor_committed_value = list(current_values)
        self._editor_options = self._normalize_options(options, current_values)
        self._editor_selected_index = 0
        self._summary_text = self._render_choice_editor(label, multi=True)

    @staticmethod
    def _normalize_options(options: list[str], current: Any) -> list[str]:
        result = [str(option) for option in options]
        current_values = current if isinstance(current, list) else [current]
        for value in current_values:
            if value in (None, ""):
                continue
            string_value = str(value)
            if string_value not in result:
                result.append(string_value)
        return result

    def _mount_text_editor(self, key: str, value: str) -> None:
        description, _type_name, _options = self._standard_field_details(key, self._form)
        field_meta = self._form.field_by_key(key)
        if field_meta is not None:
            description = field_meta.description or description
        lines = [f"[bold cyan]╸ Editing: {self._current_item.label if self._current_item else key}[/bold cyan]"]
        lines.append("")
        lines.append("")
        lines.append(f"  Current: {self._format_value(value)}")
        if description:
            lines.append(f"\n  [dim]{description}[/dim]")
            lines.append("")
        lines.append("\n[dim]Enter — confirm  ·  Esc — cancel[/dim]")
        self._summary_text = "\n".join(lines)
        if not self.is_attached:
            self.refresh()
            return
        top_lines = [f"[bold cyan]╸ Editing: {self._current_item.label if self._current_item else key}[/bold cyan]"]
        top_lines.append("")
        top_lines.append(f"  Current: {self._format_value(value)}")
        if description:
            top_lines.append(f"\n  [dim]{description}[/dim]")
        self._mount_inline_input(
            title_markup="\n".join(top_lines),
            input_value=value,
            placeholder=f"Enter {key}",
            bottom_markup="[dim]Enter — confirm  ·  Esc — cancel[/dim]",
        )

    def _mount_custom_value_input(self) -> None:
        self._editor_custom_prompt = True
        self._summary_text = (
            f"[bold cyan]╸ Add custom value[/bold cyan]\n\n"
            "[dim]Type value and press Enter[/dim]"
        )
        if not self.is_attached:
            self.refresh()
            return
        self._mount_inline_input(
            title_markup="[bold cyan]╸ Add custom value[/bold cyan]",
            input_value="",
            placeholder="Custom value",
            bottom_markup="[dim]Type value and press Enter[/dim]",
        )
        self.refresh()

    def _mount_inline_input(
        self,
        title_markup: str,
        input_value: str,
        placeholder: str,
        bottom_markup: str,
    ) -> None:
        self._summary_text = ""
        top = Static(title_markup, classes="editor-copy editor-copy--top")
        bottom = Static(bottom_markup, classes="editor-copy editor-copy--bottom")
        inp = Input(value=input_value, placeholder=placeholder, id="inline-input")
        self.mount(top)
        self.mount(inp)
        self.mount(bottom)
        inp.focus()

    def _render_choice_editor(self, label: str, multi: bool) -> str:
        lines = [f"[bold cyan]╸ Editing: {label}[/bold cyan]\n"]
        description, _type_name, _options = self._standard_field_details(self._edit_field, self._form)
        field_meta = self._form.field_by_key(self._edit_field)
        if field_meta is not None:
            description = field_meta.description or description
        current_value = self._editor_committed_value if self._editor_mode else ""
        lines.append(f"  Current: {self._format_value(current_value)}")
        if description:
            lines.append(f"\n  [dim]{description}[/dim]")
        lines.append("")
        for index, option in enumerate(self._editor_options):
            cursor = "▸" if index == self._editor_selected_index else " "
            if multi:
                mark = "●" if option in self._editor_selected_values else "○"
                lines.append(f" {cursor} {mark} {option}")
            else:
                mark = "●" if index == self._editor_selected_index else "○"
                lines.append(f" {cursor} {mark} {option}")
        if self._editor_allows_custom:
            cursor = "▸" if self._editor_selected_index == len(self._editor_options) else " "
            lines.append(f" {cursor} + Add custom value")
        lines.append("\n[dim]↑↓ navigate  Enter select/toggle  Esc cancel[/dim]")
        return "\n".join(lines)

    def is_choice_editor_active(self) -> bool:
        return self._editing and self._editor_mode in {"single_choice", "multi_choice"}

    def is_custom_input_active(self) -> bool:
        return self._editing and self._editor_custom_prompt

    @property
    def editor_mode(self) -> str:
        return self._editor_mode

    @property
    def editor_options(self) -> list[str]:
        return list(self._editor_options)

    @property
    def editor_allows_custom(self) -> bool:
        return self._editor_allows_custom

    def editor_current_value(self) -> Any:
        if self._editor_mode == "single_choice":
            if not self._editor_options:
                return ""
            return self._editor_options[self._editor_selected_index]
        if self._editor_mode == "multi_choice":
            return list(self._editor_selected_values)
        return ""

    def move_editor_up(self) -> None:
        if not self.is_choice_editor_active():
            return
        if self._editor_selected_index > 0:
            self._editor_selected_index -= 1
            self._refresh_editor_text()

    def move_editor_down(self) -> None:
        if not self.is_choice_editor_active():
            return
        max_index = len(self._editor_options) - 1 + (1 if self._editor_allows_custom else 0)
        if self._editor_selected_index < max_index:
            self._editor_selected_index += 1
            self._refresh_editor_text()

    def move_editor_selection_to(self, option: str) -> None:
        if option in self._editor_options:
            self._editor_selected_index = self._editor_options.index(option)
            self._refresh_editor_text()

    def toggle_editor_option(self) -> bool:
        if self._editor_mode != "multi_choice":
            return False
        if self._editor_selected_index >= len(self._editor_options):
            return False
        option = self._editor_options[self._editor_selected_index]
        if option in self._editor_selected_values:
            self._editor_selected_values.remove(option)
            if option not in self._form.field_by_key(self._edit_field).options:  # type: ignore[union-attr]
                self._editor_options.remove(option)
                self._editor_selected_index = min(self._editor_selected_index, max(0, len(self._editor_options) - 1))
        else:
            self._editor_selected_values.append(option)
        self._editor_committed_value = list(self._editor_selected_values)
        self._refresh_editor_text()
        return True

    def editor_activate(self) -> str:
        if self._editor_mode == "single_choice":
            if self._editor_selected_index < len(self._editor_options):
                self._editor_committed_value = self._editor_options[self._editor_selected_index]
                self._refresh_editor_text()
                return "confirm"
            return "custom"
        if self._editor_mode == "multi_choice":
            if self._editor_selected_index < len(self._editor_options):
                self.toggle_editor_option()
                return "toggle"
            return "custom"
        return "none"

    def begin_custom_value_input(self) -> None:
        if not self._editor_allows_custom:
            return
        self._mount_custom_value_input()

    def apply_custom_value(self, raw_value: str) -> bool:
        value = raw_value.strip()
        if not value:
            return False
        if value not in self._editor_options:
            self._editor_options.append(value)
        if self._editor_mode == "single_choice":
            self._editor_selected_index = self._editor_options.index(value)
            self._editor_committed_value = value
        elif self._editor_mode == "multi_choice" and value not in self._editor_selected_values:
            self._editor_selected_values.append(value)
            self._editor_selected_index = self._editor_options.index(value)
            self._editor_committed_value = list(self._editor_selected_values)
        self._editor_custom_prompt = False
        for child in list(self.children):
            child.remove()
        self._refresh_editor_text()
        return True

    def _refresh_editor_text(self) -> None:
        if not self._current_item:
            return
        self._summary_text = self._render_choice_editor(
            self._current_item.label,
            multi=self._editor_mode == "multi_choice",
        )
        self.refresh()
