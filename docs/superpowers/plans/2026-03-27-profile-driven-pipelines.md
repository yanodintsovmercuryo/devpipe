# Profile-Driven Pipelines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести `devpipe` с жёстко зашитого пайплайна на profile-driven runtime, где проект описывает `stages`, `routing`, typed `inputs`, декларативные `in`/`out` и `next_stages` через `.devpipe/profiles/*` и `.devpipe/config.yaml`.

**Architecture:** Профиль разделяется на два независимых слоя: `stages` описывают контракты данных и агентные настройки, `routing` описывает стартовую stage и правила переходов. Рантайм больше не знает про глобальный порядок стадий или кодовые `on_success`-переходы, а вычисляет следующую stage по данным `out`, `input`, `context` и декларативным правилам `next_stages`.

**Tech Stack:** Python, YAML, existing `questionary` TUI, current runner abstraction (`codex` / `claude`), existing artifact/history/config loaders.

---

### Task 1: Ввести profile runtime model с разделением `stages` и `routing`

**Files:**
- Create: `src/devpipe/profiles/stages.py`
- Create: `src/devpipe/profiles/routing.py`
- Create: `src/devpipe/profiles/loader.py`
- Test: `tests/profiles/test_stages.py`
- Test: `tests/profiles/test_routing.py`
- Test: `tests/profiles/test_loader.py`

- [ ] **Step 1: Write the failing tests for stage schema loading**

Покрыть:
- загрузку builtin profile из репозитория
- загрузку project profile из `.devpipe/profiles/<name>/pipeline.yml`
- валидацию `inputs.<key>.type`
- валидацию `inputs.<key>.default`
- валидацию `inputs.<key>.values`
- валидацию `inputs.<key>.multi`
- валидацию `inputs.<key>.custom`
- валидацию `stages.<name>.in`
- валидацию `stages.<name>.out`
- ошибку при отсутствующем `pipeline.yml`

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/profiles/test_stages.py tests/profiles/test_loader.py -q`

Expected:
- FAIL с отсутствующими моделями `StageSpec` / `InputSpec` / loader support

- [ ] **Step 3: Implement the `stages` data model**

Ввести модели в `src/devpipe/profiles/stages.py`:
- `InputSpec`
- `FieldSpec`
- `StageInBinding`
- `StageOutField`
- `StageSpec`

Минимальный контракт `inputs.<key>`:

```yaml
type: string | int
default: <scalar-or-list>
values: [<allowed-values>]
multi: true | false
custom: true | false
```

Инварианты:
- `multi: false` => `default` скаляр
- `multi: true` => `default` список
- `custom: false` => runtime value должен быть из `values`
- `custom: true` => runtime value может быть любым валидным по `type`
- `values` обязаны соответствовать `type`

- [ ] **Step 4: Write the failing tests for routing schema**

Покрыть:
- валидацию `routing.start_stage`
- валидацию ссылок `next_stages[*].stage`
- ошибку при ссылке на несуществующую stage
- правило `default: true` максимум один раз на stage
- поддерживаемые блоки условий `all` / `any`
- поддерживаемые операции `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`

- [ ] **Step 5: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/profiles/test_routing.py -q`

Expected:
- FAIL с отсутствующими моделями `RouteRule` / `RouteCondition`

- [ ] **Step 6: Implement the `routing` data model**

Ввести модели в `src/devpipe/profiles/routing.py`:
- `RouteCondition`
- `RouteRule`
- `StageRouting`
- `RoutingSpec`

Минимальный контракт:

```yaml
routing:
  start_stage: developer
  by_stage:
    developer:
      next_stages:
        - stage: qa_stand
          all:
            - field: out.implementation_done
              op: eq
              value: yes
        - stage: developer
          default: true
```

Правила:
- `next_stages` проверяются сверху вниз
- первое совпавшее правило побеждает
- если ни одно правило не совпало и `default` отсутствует, это runtime error профиля
- `field` может ссылаться только на `input.*`, `in.*`, `out.*`, `context.*`, `runtime.*`

- [ ] **Step 7: Implement profile loader**

`src/devpipe/profiles/loader.py` должен:
- загружать builtin profile из репозитория
- загружать project profile из `.devpipe/profiles/<profile_name>/`
- собирать `ProfileDefinition` из `stages` и `routing`
- валидировать связность между `routing` и `stages`

Верхнеуровневая модель:

```python
ProfileDefinition(
    name=...,
    defaults=...,
    inputs=...,
    stages=...,
    routing=...,
)
```

- [ ] **Step 8: Run tests to verify loader passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/profiles/test_stages.py tests/profiles/test_routing.py tests/profiles/test_loader.py -q`

Expected:
- PASS

- [ ] **Step 9: Commit**

```bash
git add src/devpipe/profiles/stages.py src/devpipe/profiles/routing.py src/devpipe/profiles/loader.py tests/profiles/test_stages.py tests/profiles/test_routing.py tests/profiles/test_loader.py
git commit -m "feat(profiles): add stage and routing profile models"
```

### Task 2: Перевести runtime на `routing` и rule-based `next_stages`

**Files:**
- Modify: `src/devpipe/runtime/state.py`
- Modify: `src/devpipe/runtime/transitions.py`
- Modify: `src/devpipe/runtime/engine.py`
- Modify: `src/devpipe/app.py`
- Test: `tests/e2e/test_full_pipeline.py`

- [ ] **Step 1: Write failing tests for dynamic routing**

Покрыть:
- старт с `routing.start_stage`
- переход по `next_stages[*]`
- завершение на `completed`
- возврат `qa_stand -> developer`
- корректную работу `first_stage` / `last_stage` относительно активного routing graph

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/e2e/test_full_pipeline.py -q`

Expected:
- FAIL, потому что runtime всё ещё зависит от `STAGE_ORDER` и `on_success`

- [ ] **Step 3: Replace global stage order with profile-driven routing**

Изменения:
- убрать зависимость runtime от глобального `STAGE_ORDER`
- хранить доступные `stages` и `routing` в `PipelineState` или `PipelineEngine`
- вычислять следующую stage через rule evaluator, а не через `next_stage(current_stage)`
- `app.run()` должен идти по graph профиля, а не по кодовому списку стадий

- [ ] **Step 4: Separate retries from business rerouting**

Оставить текущее поведение:
- retry policy по имени stage
- pipeline failure при исчерпании retries

Изменить поведение:
- `qa_stand -> developer` считается нормальным business transition
- retry нельзя использовать вместо `next_stages`
- возврат на доработку должен создавать новую попытку `developer` в рамках того же run

- [ ] **Step 5: Persist stage attempts in history state**

Runtime state должен хранить попытки вида:
- `stage`
- `attempt_number`
- `in_snapshot`
- `out_snapshot`
- `selected_rule`
- `next_stage`

Это нужно, чтобы TUI и history могли показать цикл `developer -> qa_stand -> developer`.

- [ ] **Step 6: Run tests to verify runtime passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/e2e/test_full_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/runtime/state.py src/devpipe/runtime/transitions.py src/devpipe/runtime/engine.py src/devpipe/app.py tests/e2e/test_full_pipeline.py
git commit -m "refactor(runtime): drive stage flow from routing rules"
```

### Task 3: Ввести декларативные `in`/`out` bindings и typed inputs

**Files:**
- Modify: `src/devpipe/stages/loader.py`
- Modify: `src/devpipe/stages/envelope.py`
- Modify: `src/devpipe/app.py`
- Create: `tests/stages/test_bindings.py`

- [ ] **Step 1: Write failing tests for stage bindings**

Покрыть:
- маппинг `input.*`
- маппинг `stage.<name>.out.*`
- маппинг `runtime.*`
- `multi: true` для `string`
- `multi: true` для `int`
- `custom: false` запрещает произвольные значения
- `custom: true` разрешает произвольные значения
- error on missing required binding

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/stages/test_bindings.py -q`

Expected:
- FAIL из-за отсутствия typed input validation и stage-aware bindings

- [ ] **Step 3: Introduce declarative binding resolver**

Поддержать источники:
- `input.<key>`
- `stage.<stage_name>.out.<field>`
- `context.shared`
- `runtime.git.current_branch`
- `integration.jira.issue`

Не вводить произвольный eval/template language. Только path-based lookups и builtin resolvers.

- [ ] **Step 4: Replace hardcoded release-specific context assembly**

Убрать из `src/devpipe/app.py` прямую сборку `release_inputs`.

Вместо этого описывать в `pipeline.yml`:
- какие поля нужны stage
- откуда они берутся через `in`
- какие поля stage обязана вернуть через `out`

- [ ] **Step 5: Make `TaskEnvelope` consume resolved stage inputs**

`build_envelope()` должен получать уже вычисленный stage context и не знать ничего о конкретных стадиях вроде `release`.

- [ ] **Step 6: Run tests to verify binding layer passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/stages/test_bindings.py tests/e2e/test_full_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/stages/loader.py src/devpipe/stages/envelope.py src/devpipe/app.py tests/stages/test_bindings.py tests/e2e/test_full_pipeline.py
git commit -m "feat(pipeline): resolve stage inputs from declarative bindings"
```

### Task 4: Сделать profile-aware CLI, TUI и project config

**Files:**
- Modify: `src/devpipe/cli.py`
- Modify: `src/devpipe/tui.py`
- Modify: `src/devpipe/project_config.py`
- Test: `tests/test_cli.py`
- Test: `tests/tui/test_profile_selection.py`

- [ ] **Step 1: Write failing tests for profile selection**

Покрыть:
- `devpipe run --profile <name>`
- fallback на builtin default profile
- project default profile из `.devpipe/config.yaml`
- ошибка при неизвестном profile name

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py tests/tui/test_profile_selection.py -q`

Expected:
- FAIL, потому что CLI/TUI не знают про profile loading

- [ ] **Step 3: Extend project config**

Добавить в `.devpipe/config.yaml`:
- `defaults.profile`
- при необходимости `available.profiles`

`load_project_config()` должен уметь:
- читать default profile
- находить project profiles из `.devpipe/profiles/*`
- отдавать список stage names активного профиля

- [ ] **Step 4: Update console CLI**

Изменения:
- добавить `--profile`
- при `run` передавать `profile_name` в `RunConfig`
- `inspect` уметь показывать `stages` и `routing` активного profile

- [ ] **Step 5: Update TUI configuration screen**

Поведение:
- в меню конфигурации добавить `Set profile`
- при смене profile полностью пересобирать экран, summary, stage-range options, input params, history
- `first_stage` / `last_stage` показывать только `stages` активного profile
- если новый profile не содержит ранее выбранные стадии или параметры, сбрасывать их

- [ ] **Step 6: Run tests to verify UI/CLI selection passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py tests/tui/test_profile_selection.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/cli.py src/devpipe/tui.py src/devpipe/project_config.py tests/test_cli.py tests/tui/test_profile_selection.py
git commit -m "feat(ui): add profile selection to cli and tui"
```

### Task 5: Разделить history по профилям и сохранять циклы stage attempts

**Files:**
- Modify: `src/devpipe/history.py`
- Modify: `src/devpipe/app.py`
- Modify: `src/devpipe/tui.py`
- Test: `tests/test_history.py`

- [ ] **Step 1: Write failing tests for profile-scoped history**

Покрыть:
- запись run в историю активного profile
- изоляцию history между двумя profile names
- сохранение нескольких попыток одной stage в одном run
- корректную загрузку history для TUI только по активному profile

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_history.py -q`

Expected:
- FAIL из-за отсутствия profile-aware history и stage attempts

- [ ] **Step 3: Change history storage shape**

Рекомендованный формат:
- отдельные файлы `~/.devpipecfg/history/<profile>.yaml`

Причины:
- проще дебажить
- нет конфликтов при частичной порче файла
- легче чистить profile-specific history

Структура записи run должна включать:
- `profile`
- `started_at`
- `finished_at`
- `status`
- `attempts[]`

- [ ] **Step 4: Thread profile name through run config**

`RunConfig` должен включать `profile`.

`save_run()` и `load_history()` должны принимать profile name явно, без скрытых глобальных fallback.

- [ ] **Step 5: Run tests to verify history passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_history.py tests/test_cli.py tests/tui/test_profile_selection.py -q`

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add src/devpipe/history.py src/devpipe/app.py src/devpipe/tui.py tests/test_history.py
git commit -m "feat(history): scope run history by profile and stage attempts"
```

### Task 6: Вынести builtin default profile и обновить DSL examples

**Files:**
- Create: `profiles/default/pipeline.yml`
- Create: `profiles/default/agents/*`
- Create: `examples/acquiring/.devpipe/config.yaml`
- Create: `examples/acquiring/.devpipe/profiles/acquiring-service/pipeline.yml`
- Create: `examples/acquiring/.devpipe/profiles/acquiring-service/agents/*`
- Modify: `README.md`

- [ ] **Step 1: Move current built-in delivery pipeline into builtin profile**

Builtin profile должен описывать текущий flow через `stages` и `routing`:
- `architect`
- `developer`
- `test_developer`
- `qa_local`
- `release`
- `qa_stand`

Все prompts и schemas должны жить рядом с profile, а не в глобальном `stages/` legacy-каталоге.

- [ ] **Step 2: Add project example for acquiring**

Положить reference example с:
- typed `inputs`
- `multi`
- `custom`
- stage-local `in` / `out`
- `routing.by_stage.<stage>.next_stages`

Example не обязан быть executable end-to-end в тестах, но должен быть синтаксически валидный и консистентный.

- [ ] **Step 3: Document the profile DSL**

README должен объяснить:
- как устроен `.devpipe/profiles/{name}/`
- как выбрать profile в CLI и TUI
- как задать default profile в `.devpipe/config.yaml`
- как описывать `inputs`
- как описывать `stages`
- как описывать `routing`
- как задавать условия в `next_stages`

- [ ] **Step 4: Run verification**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/profiles/test_stages.py tests/profiles/test_routing.py tests/profiles/test_loader.py tests/stages/test_bindings.py tests/test_history.py tests/test_cli.py tests/tui/test_profile_selection.py tests/e2e/test_full_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add profiles/default README.md examples/acquiring
git commit -m "docs(profiles): add builtin and acquiring stage-routing examples"
```

## Pipeline DSL Draft

```yaml
version: 1
name: delivery-default

defaults:
  runner: auto
  model: middle
  effort: middle

inputs:
  task:
    type: string
    default: ""
    values: []
    multi: false
    custom: true
  environment:
    type: string
    default: qa
    values: [dev, qa, prod]
    multi: false
    custom: false
  jira_ids:
    type: string
    default: []
    values: []
    multi: true
    custom: true
  retry_limit:
    type: int
    default: 2
    values: [1, 2, 3]
    multi: false
    custom: false

stages:
  developer:
    runner: codex
    model: medium
    effort: medium
    agent:
      prompt: agents/developer/prompt.md
      output_schema: agents/developer/output.schema.json
    in:
      task: input.task
      jira_ids: input.jira_ids
      shared_context: context.shared
    out:
      implementation_done:
        type: string
      changed_modules:
        type: string
      logs_attached:
        type: int
    retry_limit: 2

  qa_stand:
    runner: codex
    model: medium
    effort: medium
    agent:
      prompt: agents/qa_stand/prompt.md
      output_schema: agents/qa_stand/output.schema.json
    in:
      env: input.environment
      changed_modules: stage.developer.out.changed_modules
      shared_context: context.shared
    out:
      decision:
        type: string
      defects_count:
        type: int
      review_notes:
        type: string
    retry_limit: 1

routing:
  start_stage: developer
  by_stage:
    developer:
      next_stages:
        - stage: qa_stand
          all:
            - field: out.implementation_done
              op: eq
              value: yes
        - stage: failed
          default: true

    qa_stand:
      next_stages:
        - stage: release
          all:
            - field: out.decision
              op: eq
              value: approved
        - stage: developer
          any:
            - field: out.decision
              op: eq
              value: needs_rework
            - field: out.defects_count
              op: gt
              value: 0
        - stage: failed
          default: true
```

## Design Notes

- `next_stages` заменяет `outcomes` и `on_success/on_failure`
- business reroute (`qa_stand -> developer`) не является retry
- retry остаётся только для технического повтора той же stage
- `multi` разрешён для любого `type`
- `custom` означает, что UI может принимать значения вне `values`
