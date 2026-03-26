from __future__ import annotations

import json
import re

from jsonschema import ValidationError, validate


class OutputParseError(ValueError):
    pass


class OutputParser:
    def __init__(self, schema: dict[str, object]) -> None:
        self.schema = schema

    def parse(self, transcript: str) -> dict[str, object]:
        payload = self._extract_json(transcript)
        try:
            validate(payload, self.schema)
        except ValidationError as exc:
            raise OutputParseError(str(exc)) from exc
        return payload

    def _extract_json(self, transcript: str) -> dict[str, object]:
        fenced = re.search(r"```json\s*(\{.*?\})\s*```", transcript, re.DOTALL)
        raw = fenced.group(1) if fenced else transcript.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OutputParseError(str(exc)) from exc
        if not isinstance(data, dict):
            raise OutputParseError("Structured output must be a JSON object")
        return data

