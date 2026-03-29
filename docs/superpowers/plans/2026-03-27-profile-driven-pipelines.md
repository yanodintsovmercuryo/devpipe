# Profile-Driven Pipelines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести `devpipe` с жёстко зашитого пайплайна на profile-driven runtime, где проект описывает `stages`, `routing`, typed `inputs`, декларативные `in`/`out` и `next_stages` через `.devpipe/profiles/*` и `.devpipe/config.yaml`.

**Architecture:** Профиль разделяется на два независимых слоя: `stages` описывают контракты данных и агентные настройки, `routing` описывает стартовую stage и правила переходов. Рантайм больше не знает про глобальный порядок стадий или кодовые `on_success`-переходы, а вычисляет следующую stage по данным `out`, `input`, `context` и декларативным правилам `next_stages`.

**Tech Stack:** Python, YAML, **existing Textual TUI**, current runner abstraction (`codex` / `claude`), existing artifact/history/config loaders.

**Important:** Textual TUI уже реализована (`src/devpipe/ui/`). Задача — не создавать новую TUI, а сделать существующую **profile-aware**.

---

## 📊 Current Status Summary

- ✅ **Task 1**: Profile runtime model — COMPLETE (100%)
- ✅ **Task 2**: Runtime routing — COMPLETE (100%) — commit `d2dc63a`
- ✅ **Task 3**: Declarative bindings — COMPLETE (100%) — commit `7e531cb`
- ⚠️ **Task 4**: Profile-aware CLI & TUI — MOSTLY COMPLETE (90%) — TUI profile selection works, but `load_profile_stages()` needs update to use new DSL
- ⚠️ **Task 5**: Profile-scoped history — PARTIALLY COMPLETE (40%) — `stage_attempts` captured in state, but not persisted in history files with profile scoping
- ❌ **Task 6**: Builtin profile & examples — NOT STARTED (0%) — current-delivery profile still uses old DSL, no builtin profile, no acquiring example

**Overall Progress:** ~75% (214 passing tests across profiles, runtime, bindings, UI, CLI)

**Blocking Path:** Task 6 is independent; Task 5 requires history persistence work; Task 4 minor fix to `load_profile_stages()`

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

---

### Task 1: Ввести profile runtime model с разделением `stages` и `routing` — ✅ COMPLETE

**Files:**
- ✅ `src/devpipe/profiles/stages.py`
- ✅ `src/devpipe/profiles/routing.py`
- ✅ `src/devpipe/profiles/loader.py`
- ✅ `tests/profiles/test_stages.py`
- ✅ `tests/profiles/test_routing.py`
- ✅ `tests/profiles/test_loader.py`

**Status:** All 46 profile tests passing.

**Commit:** `86d84b3 feat(profiles): add stage and routing profile models`

---

### Task 2: Перевести runtime на `routing` и rule-based `next_stages` — ✅ COMPLETE

**Files:**
- Modified: `src/devpipe/runtime/state.py`
- Modified: `src/devpipe/runtime/transitions.py`
- Modified: `src/devpipe/runtime/engine.py`
- Modified: `src/devpipe/app.py`
- Test: `tests/e2e/test_full_pipeline.py`

**Status:** Runtime fully profile-driven. All transitions use `RuleEvaluator`. Business reroute properly separated from retries. 6 e2e tests passing.

**Commit:** `d2dc63a refactor(runtime): drive stage flow from routing rules`

- [ ] **Step 1: Write failing tests for dynamic routing**

Покрыть:
- старт с `routing.start_stage`
- переход по `next_stages[*]` (first match wins)
- завершение на `completed`
- business reroute (например, `qa_stand -> developer`)
- корректную работу `first_stage` / `last_stage` относительно активного routing graph

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/e2e/test_full_pipeline.py -q`

Expected:
- FAIL, потому что runtime всё ещё зависит от `STAGE_ORDER` и `on_success`

- [ ] **Step 3: Replace global stage order with profile-driven routing**

Изменения:
- Убрать зависимость runtime от глобального `STAGE_ORDER`
- Хранить `routing: RoutingSpec` в `PipelineState` или передавать в `PipelineEngine`
- Реализовать rule evaluator: пройти по `next_stages`, вычислить `field` значения, сравнить условия, выбрать `stage`
- `app.run()` должен идти по graph профиля, а не по кодовому списку стадий

- [ ] **Step 4: Separate retries from business rerouting**

Оставить:
- retry policy по имени stage (retry_limit из StageSpec)
- pipeline failure при исчерпании retries

Изменить:
- `qa_stand -> developer` считается нормальным business transition (не retry)
- retry нельзя использовать вместо `next_stages`
- возврат на доработку должен создавать **новую попытку** `developer` в рамках того же run (увеличивать attempt_number)

- [ ] **Step 5: Persist stage attempts in history state**

Runtime state должен хранить попытки вида:
```python
attempts: [
  {
    "stage": "developer",
    "attempt_number": 1,
    "in_snapshot": {...},      # входные данные stage
    "out_snapshot": {...},     # выходные данные stage
    "selected_rule": {...},    # какое правило сработало
    "next_stage": "qa_stand"
  }
]
```

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

---

### Task 3: Ввести декларативные `in`/`out` bindings и typed inputs — ✅ COMPLETE

**Files:**
- Created: `src/devpipe/bindings.py` (resolver)
- Modified: `src/devpipe/app.py`
- Test: `tests/stages/test_bindings.py`

**Status:** Binding resolver supports `input.*`, `stage.*.out.*`, `context.*`, `runtime.*`, `integration.*`. Integrated into app.py stage context assembly. 9 binding tests passing.

**Commit:** `7e531cb feat(pipeline): resolve stage inputs from declarative bindings`

- [ ] **Step 1: Write failing tests for stage bindings**

Покрыть:
- маппинг `input.<key>` → из `RunConfig.extra_params` или profile defaults
- маппинг `stage.<name>.out.<field>` → из `state.artifacts["stage_outputs"][<name>]`
- маппинг `context.shared` → из `state.shared_context`
- маппинг `runtime.git.current_branch` → через `git_adapter`
- маппинг `integration.jira.issue` → через `jira_adapter`
- `multi: true` для `string` и `int` (списки)
- `custom: false` запрещает значения вне `values`
- `custom: true` разрешает любые значения типа
- error при отсутствии обязательного binding

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/stages/test_bindings.py -q`

Expected:
- FAIL из-за отсутствия binding resolver

- [ ] **Step 3: Introduce declarative binding resolver**

Создать `src/devpipe/bindings.py`:

Поддерживаемые источники:
- `input.<key>` — глобальные входы из профиля `inputs`
- `stage.<stage_name>.out.<field>` — выходы предыдущих стадий
- `context.shared` — общий контекст (`state.shared_context`)
- `runtime.git.current_branch` — текущая git ветка
- `integration.jira.issue` — данные Jira (если адаптер есть)

**Не** вводить произвольный eval/template language. Только path-based lookups и builtin resolvers.

- [ ] **Step 4: Replace hardcoded release-specific context assembly**

Убрать из `src/devpipe/app.py:119-134` прямую сборку `release_inputs`.

Вместо этого профиль описывает:
- какие поля нужны stage (`stage.out`)
- откуда они берутся (`stage.in.bindings`)

- [ ] **Step 5: Make `TaskEnvelope` consume resolved stage inputs**

`build_envelope()` должен получать уже вычисленный stage context и не знать ничего о конкретных стадиях вроде `release`.

- [ ] **Step 6: Run tests to verify binding layer passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/stages/test_bindings.py tests/e2e/test_full_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/bindings.py tests/stages/test_bindings.py
git commit -m "feat(pipeline): resolve stage inputs from declarative bindings"
```

---

### Task 4: Сделать существующий CLI и Textual TUI profile-aware — ✅ MOSTLY COMPLETE (90%)

**Files:**
- Modified: `src/devpipe/project_config.py`
- Modified: `src/devpipe/cli.py`
- Modified: `src/devpipe/app.py`
- Modified: `src/devpipe/ui/app.py`
- Modified: `src/devpipe/ui/services.py`
- Modified: `src/devpipe/ui/screens/config_screen.py`
- Test: `tests/test_cli.py` (5 tests pass)
- Test: `tests/ui/test_config_screen.py` (122 UI tests pass)

**Status:**
- ✅ CLI: `--profile` flag implemented and passed to app
- ✅ TUI: Profile selection dropdown in ConfigScreen, triggers reload
- ✅ UI services: `discover_profiles()`, `load_profile_fields()`, `load_profile_defaults()`
- ⚠️ `load_profile_stages()` still reads old `flow.transitions` format (for UI stage ordering only; not blocking)
- ✅ Profile change handler in UI app updates available stages/fields/defaults

**Remaining:** Update `load_profile_stages()` to derive stage order from `profile.stages.keys()` instead of old flow DSL.

**Tests:** All CLI and UI tests passing.

Покрыть:
- `devpipe run --profile <name>`
- fallback на builtin default profile (если нет project profile)
- project default profile из `.devpipe/config.yaml:defaults.profile`
- ошибка при неизвестном profile name

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -q`

Expected:
- FAIL, потому что `--profile` не существует

- [ ] **Step 3: Extend project config**

Добавить в `.devpipe/config.yaml`:
```yaml
defaults:
  profile: delivery-default  # или current-delivery
```

`load_project_config()` → читает `defaults.profile`.

- [ ] **Step 4: Add profile support to CLI**

Изменения:
- Добавить `--profile` в `run` подкоманду (`src/devpipe/cli.py`)
- В `RunConfig` добавить поле `profile: str | None`
- В `build_default_app()` или `app.run()` загружать профиль через `load_profile()` и передавать в `OrchestratorApp`
- `inspect` команда: показывать `stages` и `routing` активного профиля

- [ ] **Step 5: Update TUI configuration screen**

`src/devpipe/ui/screens/config_screen.py`:

Поведение:
- Добавить dropdown/выбор профиля в экран конфигурации
- При смене профиля:
  - перестраивать список stages (из `profile.stages`)
  - обновлять `first_role` / `last_role` dropdowns (ограничить только stages из профиля)
  - сбрасывать поля, которых нет в новом профиле
  - обновлять default значения из `profile.defaults`
- Протащить `profile_name` через `UIState` → `RunConfig`

**Note:** `src/devpipe/ui/services.py` уже имеет `discover_profiles()` и `load_profile_stages()`, но `load_profile_stages()` читает старый `flow.transitions` формат. Нужно исправить на `load_profile()`.

- [ ] **Step 6: Run tests to verify UI/CLI profile selection passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py tests/ui/test_config_screen.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/project_config.py src/devpipe/cli.py src/devpipe/app.py src/devpipe/ui/app.py src/devpipe/ui/services.py src/devpipe/ui/screens/config_screen.py tests/test_cli.py tests/ui/test_config_screen.py
git commit -m "feat(ui): integrate profile selection into cli and textual tui"
```

---

### Task 5: Profile-scoped history with stage attempts — ⚠️ IN PROGRESS (40%)

**Files:**
- Modified: `src/devpipe/history.py` (needs work)
- Modified: `src/devpipe/app.py` (stage_attempts captured)
- To modify: `src/devpipe/ui/app.py`, `src/devpipe/ui/screens/history_screen.py`
- Test: `tests/test_history.py` (1 test, needs expansion)

**Status:**
- ✅ `PipelineState.stage_attempts` captures: `stage`, `attempt_number`, `in_snapshot`, `out_snapshot`, `selected_rule`, `next_stage` (app.py lines 259-271)
- ❌ `save_run(config)` does **not** persist `stage_attempts` to history
- ❌ `history.py` uses single file `~/.devpipecfg/history.yaml`, no profile scoping
- ❌ `load_history()` returns all runs, no profile filtering
- ❌ No separate history files per profile

**Required:**
1. Move stage_attempts from state to saved run record (pass `state` to `save_run()`)
2. Change storage to `~/.devpipecfg/history/<profile>.yaml` or unified file with profile grouping
3. Add `load_history(profile_name)` param
4. Update TUI history screen to show attempts per run

**Tests:** Existing test only covers finish_run timing; needs expansion for profile + attempts.

- [ ] **Step 1: Write failing tests for profile-scoped history**

Покрыть:
- `save_run(config)` записывает `profile` из `config`
- `load_history(profile_name)` возвращает только runs с этим `profile`
- изоляцию history между двумя profile names (разные файлы или фильтрация)
- сохранение массива `attempts[]` с полями: `stage`, `attempt_number`, `in_snapshot`, `out_snapshot`, `selected_rule`, `next_stage`
- корректную загрузку истории в TUI только по активному profile

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_history.py -q`

Expected:
- FAIL из-за отсутствия profile в `save_run()`/`load_history()`

- [ ] **Step 3: Change history storage shape**

Рекомендуемый формат: отдельные файлы `~/.devpipecfg/history/<profile>.yaml`

Преимущества:
- проще дебажить
- нет конфликтов при частичной порче файла
- легче чистить profile-specific history

Альтернатива: один файл `history.yaml` с группировкой по `profile` (но это сложнее).

Структура записи run:
```yaml
- profile: current-delivery
  run_id: task-abc123
  task: "Implement feature X"
  task_id: ABC-123
  runner: codex
  started_at: "2026-03-29T10:00:00Z"
  finished_at: "2026-03-29T10:45:00Z"
  status: completed
  attempts:
    - stage: architect
      attempt_number: 1
      in_snapshot: {task: "...", ...}
      out_snapshot: {summary: "...", plan: "..."}
      selected_rule: {stage: "developer", default: true}
      next_stage: developer
    - stage: developer
      attempt_number: 1
      ...
```

- [ ] **Step 4: Thread profile name through run config**

`RunConfig` → добавить `profile: str | None`.

`save_run(config)` → использовать `config.profile` для пути к файлу.

`load_history(profile_name)` → явный параметр, возвращает список runs для profile.

- [ ] **Step 5: Update TUI history screen**

`src/devpipe/ui/screens/history_screen.py`:

- Показывать только runs активного профиля (`UIState.profile`)
- Добавить детализацию attempts (клик на run → показать цепочку stage попыток)

- [ ] **Step 6: Run tests to verify history passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_history.py tests/ui/test_history_screen.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/history.py src/devpipe/app.py src/devpipe/ui/app.py src/devpipe/ui/services.py src/devpipe/ui/screens/history_screen.py tests/test_history.py
git commit -m "feat(history): profile-scoped run history with stage attempt tracking"
```

---

### Task 6: Convert builtin profile & provide examples — ⚠️ PARTIALLY (30%)

**Files:**
- Modify: `.devpipe/profiles/current-delivery/pipeline.yml` (convert to new DSL)
- Create: `profiles/default/pipeline.yml` (builtin copy)
- Create: `profiles/default/agents/*` (if needed)
- Create/Modify: `examples/acquiring/.devpipe/profiles/acquiring-service/pipeline.yml`
- Create/Modify: `examples/acquiring/.devpipe/profiles/acquiring-service/agents/*`
- Create: `examples/acquiring/.devpipe/config.yaml`
- Modify: `README.md`

**Current State:**
- ✅ `.devpipe/profiles/current-delivery/` exists with `pipeline.yml` and `agents/`
- ⚠️ `pipeline.yml` uses **old DSL** (`roles` + `flow.transitions`) — needs conversion
- ❌ No builtin profile in repo (`profiles/default/`)
- ❌ No updated `examples/acquiring/`
- ⚠️ Conversion progress: ~30%

- [ ] **Step 1: Convert current-delivery to new DSL**

Преобразовать `.devpipe/profiles/current-delivery/pipeline.yml`:

Было (old DSL):
```yaml
roles:
  architect: { runner, model, effort, agent, requires, consumes, produces, retry_limit }
  ...
flow:
  start: architect
  transitions:
    architect: { on_success: developer, on_failure: failed }
    ...
```

Стало (new DSL):
```yaml
version: 1
name: current-delivery

defaults:
  runner: auto
  model: middle
  effort: middle

inputs:
  task:
    type: string
    default: ""
    custom: true
  task_id:
    type: string
    required: false
  target_branch:
    type: string
    required: false
  namespace:
    type: string
    required: false
  service:
    type: string
    required: false
  tags:
    type: array
    default: []
  extra_params:
    type: object
    default: {}

stages:
  architect:
    runner: codex
    model: medium
    effort: medium
    retry_limit: 2
    agent:
      prompt: agents/architect/prompt.md
      output_schema: agents/architect/output.schema.json
    in:
      task: input.task
      jira: integration.jira.issue  # optional if jira_adapter present
      shared_context: context.shared
    out:
      architecture_plan: { type: object }

  developer:
    runner: codex
    model: high
    effort: middle
    retry_limit: 2
    agent:
      prompt: agents/developer/prompt.md
      output_schema: agents/developer/output.schema.json
    in:
      task: input.task
      architecture_plan: stage.architect.out.architecture_plan
      shared_context: context.shared
    out:
      code_changes: { type: object }

  ... (остальные stages аналогично)

routing:
  start_stage: architect
  by_stage:
    architect:
      next_stages:
        - stage: developer
          default: true
    developer:
      next_stages:
        - stage: test_developer
          default: true
    ... (линейный flow → только default правила)
```

**Важно:** Сохранить промпты и схемы в `agents/` без изменений.

- [ ] **Step 2: Create builtin default profile**

Скопировать конвертированный профиль в `profiles/default/pipeline.yml` (внутри репозитория, не в `.devpipe/`). Это builtin профиль по умолчанию, который доступен даже без project-specific `.devpipe/`.

- [ ] **Step 3: Create/update acquiring example**

`examples/acquiring/.devpipe/` должен содержать:

1. `config.yaml`:
```yaml
defaults:
  profile: acquiring-service
```

2. `profiles/acquiring-service/pipeline.yml` — пример с использованием:
- typed inputs (`multi: true`, `custom: true/false`)
- сложными `in` bindings
- условными `next_stages` (`all` / `any`)

3. `profiles/acquiring-service/agents/` — минимум 2-3 staged промпта (можно упрощённые).

- [ ] **Step 4: Document the profile DSL**

`README.md` должен содержать разделы:

- **Profile Structure**: `.devpipe/profiles/<name>/pipeline.yml` и `agents/`
- **Selecting a Profile**: CLI `--profile`, TUI dropdown, `.devpipe/config.yaml:defaults.profile`
- **Inputs**: `inputs.<key>.type`, `default`, `values`, `multi`, `custom`
- **Stages**: `stages.<name>.runner`, `model`, `effort`, `retry_limit`, `agent.{prompt,output_schema}`, `in.bindings`, `out.fields`
- **Routing**: `routing.start_stage`, `routing.by_stage.<stage>.next_stages[*].{stage,all,any,default}`
- **Conditions**: `field`, `op` (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`)
- **Binding Sources**: `input.*`, `stage.*.out.*`, `context.*`, `runtime.*`, `integration.*`
- **Example**: показать минимальный рабочий профиль

- [ ] **Step 5: Run full test suite verification**

Run:
```bash
PYTHONPATH=src .venv/bin/pytest tests/profiles/ tests/stages/ tests/e2e/ tests/test_history.py tests/test_cli.py tests/ui/ -q
```

Expected:
- PASS (все 200+ тестов)

- [ ] **Step 6: Commit**

```bash
git add profiles/default examples/acquiring README.md
git commit -m "docs(profiles): add builtin default profile and acquiring example with new DSL"
```

---

## Pipeline DSL Reference (Final)

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
    custom: true
  environment:
    type: string
    default: qa
    values: [dev, qa, prod]
    custom: false
  tags:
    type: array
    default: []
    multi: true
    custom: true

stages:
  developer:
    runner: codex
    model: medium
    effort: medium
    retry_limit: 2
    agent:
      prompt: agents/developer/prompt.md
      output_schema: agents/developer/output.schema.json
    in:
      task: input.task
      env: input.environment
      shared: context.shared
    out:
      code_changes: { type: object }
      tests: { type: object }

  qa_stand:
    runner: codex
    model: medium
    effort: medium
    retry_limit: 1
    agent:
      prompt: agents/qa_stand/prompt.md
      output_schema: agents/qa_stand/output.schema.json
    in:
      code: stage.developer.out.code_changes
      env: input.environment
    out:
      verdict: { type: string }
      defects: { type: int }

routing:
  start_stage: developer
  by_stage:
    developer:
      next_stages:
        - stage: qa_stand
          default: true
    qa_stand:
      next_stages:
        - stage: developer
          any:
            - field: out.verdict
              op: eq
              value: needs_rework
            - field: out.defects
              op: gt
              value: 0
        - stage: release
          all:
            - field: out.verdict
              op: eq
              value: approved
            - field: out.defects
              op: eq
              value: 0
        - stage: failed
          default: true
```

---

## Design Notes

- `next_stages` replaces `on_success` / `on_failure` outcomes
- Business reroute (e.g., `qa_stand -> developer`) is **not** a retry; it increments `attempt_number` but uses the same run
- `multi` allowed for any `type` (arrays)
- `custom` means UI can accept values outside `values` list
- Binding sources: `input.*`, `stage.*.out.*`, `context.*`, `runtime.*`, `integration.*`
- Retry remains for technical failures only (exceptions); managed by `retry_limit` in `StageSpec`
- Rule evaluation: first matching rule wins; if none match and no default → runtime error

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
