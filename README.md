# devpipe

Event-driven orchestration runtime for six-stage delivery workflows: `architect`, `developer`, `test_developer`, `qa_local`, `release`, `qa_stand`.

## Install

```bash
python -m venv .venv
./.venv/bin/pip install -e .
```

## Run

```bash
./.venv/bin/python -m devpipe run \
  --task "Implement feature" \
  --runner codex \
  --stand u1 \
  --dataset s4-3ds \
  --service acquiring
```

`--task-id` is optional. When provided, Jira context is loaded and attached to the first stage. When omitted, the pipeline runs without Jira context.

```bash
./.venv/bin/python -m devpipe run \
  --task-id MRC-123 \
  --task "Implement feature" \
  --runner codex \
  --stand u1 \
  --dataset s4-3ds \
  --service acquiring
```

## Partial runs

Use `--first-role` and `--last-role` to run a slice of the pipeline:

```bash
# Stop after developer stage (no namespace required)
./.venv/bin/python -m devpipe run \
  --task "Implement feature" \
  --runner codex \
  --last-role developer

# Run only test_developer
./.venv/bin/python -m devpipe run \
  --task "Implement feature" \
  --runner codex \
  --first-role test_developer \
  --last-role test_developer

# Start from qa_local through the end
./.venv/bin/python -m devpipe run \
  --task "Implement feature" \
  --runner codex \
  --first-role qa_local \
  --stand u1 \
  --dataset s4-3ds \
  --service acquiring
```

Available roles in order: `architect`, `developer`, `test_developer`, `qa_local`, `release`, `qa_stand`.

Namespace (`--namespace` or `config/namespace-map.yaml`) is only required when `release` or `qa_stand` are in the effective stage range.

## Inspect roles

```bash
./.venv/bin/python -m devpipe inspect --roles-dir roles
```

## Namespace mapping

Namespace resolution order is `--namespace` first, then `config/namespace-map.yaml`. If no mapping exists and the run includes `release` or `qa_stand`, the run fails loudly.

## Degraded modes

- Jira context is skipped when `--task-id` is not provided.
- Jira adapter can return unavailable context without stopping the pipeline.
- Missing namespace mapping stops release preparation.
- GitHub workflow failures stop after release stage.
- Kubernetes readiness timeouts stop before stand verification.
