"""Rule-based stage routing evaluation."""
from __future__ import annotations

from typing import Any

from devpipe.profiles.routing import RoutingSpec, RouteRule, RouteCondition


class RuleEvaluator:
    """Evaluates routing rules to determine the next stage."""

    def __init__(self, routing: RoutingSpec) -> None:
        self.routing = routing

    def evaluate(self, current_stage: str, context: dict[str, Any]) -> str:
        """
        Evaluate next stage based on current stage and context.

        Args:
            current_stage: Name of the stage that just completed
            context: Dictionary with keys:
                - inputs: dict of global input values
                - stages: dict mapping stage names to their output dicts
                - context: shared context dict
                - runtime: runtime info (git, etc)
                - integration: integration data (jira, etc)

        Returns:
            Name of the next stage to execute

        Raises:
            RuntimeError: If no rule matches and no default exists
        """
        if current_stage not in self.routing.by_stage:
            raise RuntimeError(f"Stage '{current_stage}' not defined in routing")

        stage_routing = self.routing.by_stage[current_stage]

        for rule in stage_routing.next_stages:
            if self._rule_matches(rule, current_stage, context):
                # Store the matched rule in context for recording
                context.setdefault("_last_matched_rule", {})
                context["_last_matched_rule"] = {
                    "stage": rule.stage,
                    "default": rule.default,
                    "conditions": rule.all or rule.any,
                }
                return rule.stage

        # No rule matched - check for default
        defaults = [r for r in stage_routing.next_stages if r.default]
        if defaults:
            # Store default rule
            context.setdefault("_last_matched_rule", {})
            context["_last_matched_rule"] = {
                "stage": defaults[0].stage,
                "default": True,
                "conditions": None,
            }
            return defaults[0].stage

        raise RuntimeError(f"No matching rule and no default for stage '{current_stage}'")

    def _rule_matches(self, rule: RouteRule, current_stage: str, context: dict[str, Any]) -> bool:
        """Check if a rule's conditions match the context."""
        conditions = rule.all or rule.any
        if not conditions:
            return False

        results = [self._eval_condition(cond, current_stage, context) for cond in conditions]
        return all(results) if rule.all else any(results)

    def _eval_condition(self, cond: RouteCondition, current_stage: str, context: dict[str, Any]) -> bool:
        """Evaluate a single condition."""
        actual = self._resolve_field(cond.field, current_stage, context)
        return self._apply_op(actual, cond.op, cond.value)

    def _resolve_field(self, field: str, current_stage: str, context: dict[str, Any]) -> Any:
        """
        Resolve a field reference to its actual value.

        Supported prefixes:
        - input.<key> / in.<key> => context['inputs'][<key>]
        - stage.<stage_name>.out.<field> => context['stages'][<stage_name>][<field>]
        - out.<field> => context['stages'][current_stage][<field>]
        - context.<key> => context['context'][<key>]
        - runtime.<key> => context['runtime'][<key>]
        - integration.<key> => context['integration'][<key>]
        """
        # Handle both "input." and "in." as input namespace
        if field.startswith("input.") or field.startswith("in."):
            key = field.split(".", 1)[1]
            return context["inputs"].get(key)

        if field.startswith("stage."):
            # Format: stage.<stage_name>.[out.]<field>
            parts = field.split(".")
            if len(parts) < 3:
                raise ValueError(f"Invalid stage field reference: {field}")
            stage_name = parts[1]
            remainder = ".".join(parts[2:])
            if remainder.startswith("out."):
                field_name = remainder[4:]
            else:
                field_name = remainder
            stage_outputs = context["stages"].get(stage_name, {})
            return stage_outputs.get(field_name)

        if field.startswith("out."):
            field_name = field[4:]
            stage_outputs = context["stages"].get(current_stage, {})
            return stage_outputs.get(field_name)

        if field.startswith("context."):
            key = field[8:]
            return context["context"].get(key)

        if field.startswith("runtime."):
            key = field[8:]
            return context["runtime"].get(key)

        if field.startswith("integration."):
            key = field[12:]
            return context["integration"].get(key)

        raise ValueError(f"Unsupported field prefix in: {field}")

    def _apply_op(self, actual: Any, op: str, expected: Any) -> bool:
        """Apply comparison operator."""
        if op == "eq":
            return actual == expected
        if op == "neq":
            return actual != expected
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
        if op == "in":
            return actual in expected
        if op == "contains":
            if isinstance(actual, str):
                return expected in actual
            if isinstance(actual, list):
                return expected in actual
            return False
        raise ValueError(f"Unsupported operator: {op}")
