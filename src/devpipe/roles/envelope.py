from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from devpipe.roles.loader import RoleDefinition
from devpipe.runtime.state import PipelineState


@dataclass
class TaskEnvelope:
    role: str
    goal: str
    instructions: str
    context: dict[str, object]
    artifacts: dict[str, object]
    constraints: list[str]
    output_schema: dict[str, object]


RULES_FILE_NAMES = {
    "architect": "ARCHITECT_RULES.md",
    "developer": "DEVELOPER_RULES.md",
    "test_developer": "TEST_DEVELOPER_RULES.md",
    "qa_local": "QA_LOCAL_RULES.md",
    "release": "RELEASE_RULES.md",
    "qa_stand": "QA_STAND_RULES.md",
}

BUILTIN_TAGS_DIR = Path(__file__).resolve().parents[3] / "tags"


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


def _read_rules_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def compose_role_instructions(
    base_prompt: str,
    role_name: str,
    project_root: str | Path | None = None,
    tags: list[str] | None = None,
) -> str:
    instructions = base_prompt.strip()
    if project_root is None:
        return instructions

    composer_dir = Path(project_root) / ".devpipe"
    rules_file_name = RULES_FILE_NAMES.get(role_name)
    if not rules_file_name:
        return instructions

    sections: list[str] = []

    role_rules = _read_rules_file(composer_dir / rules_file_name)
    if role_rules:
        sections.append(f"## Project-Specific Rules\n\n{role_rules}")

    for tag in tags or []:
        tagged_rules = _read_rules_file(BUILTIN_TAGS_DIR / tag / rules_file_name)
        if tagged_rules:
            sections.append(f"## Tagged Rules: {tag}\n\n{tagged_rules}")

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
