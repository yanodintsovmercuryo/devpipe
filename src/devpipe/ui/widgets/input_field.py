"""Input field renderers/editors for different FieldKind types.

Handles: string, int, select, multi_select, array, object.
"""
from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Label, Select, Static

from devpipe.ui.state import FieldKind


class InputField(Widget):
    """Renders an appropriate editor widget for a given FieldKind."""

    DEFAULT_CSS = """
    InputField {
        height: auto;
        padding: 0 0 1 0;
    }
    InputField .field-label {
        color: $text-muted;
        margin-bottom: 0;
    }
    """

    class ValueSubmitted(Message):
        """Emitted when user confirms a value."""
        def __init__(self, key: str, value: Any) -> None:
            super().__init__()
            self.key = key
            self.value = value

    def __init__(
        self,
        key: str,
        label: str,
        kind: FieldKind,
        value: Any = "",
        options: list[str] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.field_key = key
        self.field_label = label
        self.field_kind = kind
        self.field_value = value
        self.field_options = options or []

    def compose(self) -> ComposeResult:
        yield Label(self.field_label, classes="field-label")
        if self.field_kind == FieldKind.SELECT:
            opts = [(o, o) for o in self.field_options]
            if self.field_value in self.field_options:
                yield Select(opts, value=self.field_value, allow_blank=False, id=f"input-{self.field_key}")
            else:
                yield Select(opts, allow_blank=True, id=f"input-{self.field_key}")
        elif self.field_kind == FieldKind.MULTI_SELECT:
            # Render as comma-separated text input
            if isinstance(self.field_value, list):
                text = ", ".join(str(v) for v in self.field_value)
            else:
                text = str(self.field_value) if self.field_value else ""
            yield Input(
                value=text,
                placeholder=f"Comma-separated values ({', '.join(self.field_options)})",
                id=f"input-{self.field_key}",
            )
        elif self.field_kind == FieldKind.INT:
            yield Input(
                value=str(self.field_value) if self.field_value else "",
                placeholder="Enter integer",
                type="integer",
                id=f"input-{self.field_key}",
            )
        elif self.field_kind == FieldKind.ARRAY:
            if isinstance(self.field_value, list):
                text = ", ".join(str(v) for v in self.field_value)
            else:
                text = str(self.field_value) if self.field_value else ""
            yield Input(
                value=text,
                placeholder="Comma-separated values",
                id=f"input-{self.field_key}",
            )
        elif self.field_kind == FieldKind.OBJECT:
            if isinstance(self.field_value, dict):
                text = ", ".join(f"{k}={v}" for k, v in self.field_value.items())
            else:
                text = str(self.field_value) if self.field_value else ""
            yield Input(
                value=text,
                placeholder="key=value pairs, comma-separated",
                id=f"input-{self.field_key}",
            )
        else:
            # STRING or default
            yield Input(
                value=str(self.field_value) if self.field_value else "",
                placeholder=f"Enter {self.field_label.lower()}",
                id=f"input-{self.field_key}",
            )

    def parse_value(self, raw: Any) -> Any:
        """Convert raw editor value to the appropriate type."""
        if self.field_kind == FieldKind.INT:
            try:
                return int(raw)
            except (ValueError, TypeError):
                return 0
        elif self.field_kind in (FieldKind.MULTI_SELECT, FieldKind.ARRAY):
            if isinstance(raw, str):
                return [v.strip() for v in raw.split(",") if v.strip()]
            return list(raw) if raw else []
        elif self.field_kind == FieldKind.OBJECT:
            if isinstance(raw, str):
                result = {}
                for pair in raw.split(","):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        result[k.strip()] = v.strip()
                return result
            return dict(raw) if raw else {}
        return raw
