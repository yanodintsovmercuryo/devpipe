from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devpipe.roles.loader import RoleDefinition
from devpipe.runtime.state import PipelineState

BUILTIN_TAGS_DIR = Path(__file__).resolve().parents[3] / "tags"


@dataclass
class TaskEnvelope:
    role: str
    goal: str
    instructions: str
    context: dict[str, object]
    artifacts: dict[str, object]
    constraints: list[str]
    output_schema: dict[str, object]


@dataclass
class TaskResult:
    ok: bool
    summary: str
    structured_output: dict[str, object]
    artifacts: dict[str, object] = field(default_factory=dict)
    next_hints: list[str] = field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    transcript: str = ""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def compose_role_instructions(
    base_prompt: str,
    role_name: str,
    project_root: str | Path | None = None,
    tags: list[str] | None = None,
) -> str:
    instructions = base_prompt.strip()
    if project_root is None:
        return instructions

    root = Path(project_root)
    sections: list[str] = []

    # Project-level rules: .devpipe/<role>/rules.md
    project_rules = _read(root / ".devpipe" / role_name / "rules.md")
    if project_rules:
        sections.append(f"## Project Rules\n\n{project_rules}")

    for tag in tags or []:
        # Custom tag rules: .devpipe/tags/<tag>/<role>/rules.md
        custom = _read(root / ".devpipe" / "tags" / tag / role_name / "rules.md")
        if custom:
            sections.append(f"## Tag Rules: {tag}\n\n{custom}")
            continue
        # Builtin tag rules: tags/<tag>/<role>/rules.md
        builtin = _read(BUILTIN_TAGS_DIR / tag / role_name / "rules.md")
        if builtin:
            sections.append(f"## Tag Rules: {tag}\n\n{builtin}")

    if not sections:
        return instructions
    return f"{instructions}\n\n" + "\n\n".join(sections)


def build_envelope(
    role: RoleDefinition,
    state: PipelineState,
    extra_context: dict[str, object] | None = None,
    project_root: str | Path | None = None,
    tags: list[str] | None = None,
) -> TaskEnvelope:
    context = {
        "task_id": state.task_id,
        "task_text": state.task_text,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "shared_context": state.shared_context,
        "release_context": state.release_context,
    }
    if extra_context:
        context.update(extra_context)

    return TaskEnvelope(
        role=role.name,
        goal=f"Execute stage {role.name} for task {state.task_id}",
        instructions=compose_role_instructions(role.prompt, role.name, project_root=project_root, tags=tags),
        context=context,
        artifacts=state.artifacts,
        constraints=["Return machine-readable JSON matching output_schema."],
        output_schema=role.output_schema,
    )
