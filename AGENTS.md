# AGENTS Instructions

## Language
- Communicate with the user in Russian.
- Write code comments and documentation in the style requested by the user for the task.

## Scope
These instructions apply to the entire repository.

## Rule Priority
If rules conflict, use this order:
1. `AGENTS.md`
2. Task-specific user instructions in the current chat

## Operational Requirements
- Keep changes minimal and targeted to the request.
- Do not weaken tests or validations.
- When fixing tests, change test code only unless the user explicitly allows production code changes.
- Preserve existing architecture boundaries and package organization.

## Context Loading

**IMPORTANT: Rules must be loaded as the VERY FIRST action — before any reasoning, planning, tool calls, or writing code. Do not start thinking about the task until rules are loaded.**

- Upon receiving ANY request — read all files listed in "Always-Apply Rule Sources" first.
- This applies to all tasks: code changes, monitoring, infrastructure, documentation — everything.
- After loading, print exactly one line with loaded paths only (no descriptions, no missing files):
  Loaded rules: `<path1>`, `<path2>`, `<path3>`
- After reading each rule file, internally compress it: keep only actionable directives, constraints, and patterns. Do not output full rule contents unless explicitly asked.
- The loaded-rules line must appear before any actions or changes.

## Testing
- Run relevant tests for modified areas whenever possible.
- Report what was run and what could not be run.
