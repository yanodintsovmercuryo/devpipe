# Textual UI Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести весь пользовательский слой `devpipe` на `Textual` и реализовать утверждённый UX-контракт `Command Palette + Summary Pane`: слева стабильная колонка `Standard / Custom / Actions`, справа inline-edit/detail pane, снизу единая status bar, во время запуска слева timeline stage attempts, справа logs/progress.

**Architecture:** Новый UI строится вокруг `UIState` и screen-local view logic. Rendering слой на `Textual` не должен знать про YAML, history storage, git или runtime internals; он работает через typed state, actions и services. Конфигурационный экран остаётся стабильным по структуре, а variability от profile-driven runtime уходит в плоский список `Custom` полей и в detail pane.

**Tech Stack:** Python, Textual, Textual testing tools, existing `argparse` CLI, current `RunConfig`, profile loader, history loader, runtime event callbacks.

---

## Approved UX Contract

### Main Screen Layout

- Левая колонка:
  - `Standard`
  - `Profile`
  - `Task`
  - `Runner`
  - `Start Stage`
  - `Finish Stage`
  - `Custom`
  - все profile-driven `inputs` плоским списком
  - `Actions`
  - `History`
  - `Run Pipeline`
- Правая панель:
  - detail/summary pane для текущего пункта
  - inline-edit прямо в панели, без открытия отдельного экрана на каждое поле
- Нижняя строка:
  - shortcuts
  - contextual help
  - readiness / validation / run stats

### Interaction Rules

- `Up/Down` двигают курсор по левой колонке
- `Enter` открывает или подтверждает редактирование справа
- `Tab` переключает фокус между navigation и detail pane
- `Esc` отменяет локальное редактирование или возвращает из вложенного режима
- `Ctrl+H` открывает history
- `Ctrl+R` запускает pipeline, если форма валидна

### Visual Direction

- стиль `Operator Console`
- графитовый тёмный фон
- акцентный `cyan/teal` для focus и active state
- зелёный только для success
- янтарный для warning
- красный для validation/error
- тонкие рамки, плотная сетка, без декоративного шума

### Run Screen Layout

- Левая колонка:
  - timeline выполнения с stage attempts
  - примеры: `developer #1`, `qa_stand #1`, `developer #2`
- Правая панель:
  - run metadata
  - log viewer
  - краткий stage result / selected routing rule / next stage
- Нижняя строка:
  - run-mode shortcuts
  - current stage status
  - elapsed time

---

## File Structure

- `src/devpipe/ui/app.py`
  - корневой `Textual` app
- `src/devpipe/ui/state.py`
  - `UIState`, `FormState`, `RunViewState`, derived view models
- `src/devpipe/ui/actions.py`
  - pure state transitions
- `src/devpipe/ui/services.py`
  - адаптеры к profiles, history, project config и runtime launch
- `src/devpipe/ui/screens/config_screen.py`
  - основной экран `Command Palette + Summary Pane`
- `src/devpipe/ui/screens/history_screen.py`
  - отдельный экран history и restore
- `src/devpipe/ui/screens/run_screen.py`
  - timeline + logs + run metadata
- `src/devpipe/ui/widgets/nav_list.py`
  - левая колонка с секциями `Standard / Custom / Actions`
- `src/devpipe/ui/widgets/detail_panel.py`
  - правая панель с inline-edit и summary states
- `src/devpipe/ui/widgets/status_bar.py`
  - нижняя живая status line
- `src/devpipe/ui/widgets/input_field.py`
  - renderer/editor для `string`, `int`, `multi`, `custom`
- `src/devpipe/ui/widgets/stage_timeline.py`
  - timeline stage attempts на run screen
- `src/devpipe/ui/widgets/log_viewer.py`
  - лог viewer с follow-tail
- `src/devpipe/ui/widgets/history_preview.py`
  - preview history записи
- `src/devpipe/ui/run_session.py`
  - bridge между `Textual` UI и `OrchestratorApp.run()`

Изменяемые текущие файлы:

- `src/devpipe/cli.py`
- `src/devpipe/tui.py`
- `src/devpipe/app.py`
- `src/devpipe/history.py`

Новые тесты:

- `tests/ui/test_state.py`
- `tests/ui/test_actions.py`
- `tests/ui/test_config_screen.py`
- `tests/ui/test_history_screen.py`
- `tests/ui/test_run_screen.py`
- `tests/test_cli.py`

### Task 1: Ввести UI state model под утверждённый layout

**Files:**
- Create: `src/devpipe/ui/state.py`
- Create: `src/devpipe/ui/actions.py`
- Create: `src/devpipe/ui/services.py`
- Test: `tests/ui/test_state.py`
- Test: `tests/ui/test_actions.py`

- [ ] **Step 1: Write the failing tests for the main UI state**

Покрыть:
- построение левой колонки с секциями `Standard`, `Custom`, `Actions`
- отделение стандартных полей от profile-driven custom inputs
- плоский список custom полей без stage grouping
- derived state для detail pane
- readiness state для status bar
- загрузку history entry в form state
- сброс невалидных значений при смене profile

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_state.py tests/ui/test_actions.py -q`

Expected:
- FAIL с отсутствующими `UIState` и reducers

- [ ] **Step 3: Implement the pure UI state layer**

Ввести модели:
- `NavItem`
- `NavSection`
- `FieldEditorState`
- `FormState`
- `StatusBarState`
- `RunViewState`
- `UIState`

Ввести действия:
- `load_defaults`
- `select_nav_item`
- `select_profile`
- `set_field_value`
- `begin_inline_edit`
- `cancel_inline_edit`
- `apply_inline_edit`
- `apply_history_entry`
- `start_run`
- `append_run_output`
- `complete_stage_attempt`
- `finish_run`

Требования:
- никакого `Textual` или terminal I/O
- state должен работать от profile metadata, а не от старых `roles` / `STAGE_ORDER`
- `Task ID` не должен быть standard field по умолчанию

- [ ] **Step 4: Run tests to verify state layer passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_state.py tests/ui/test_actions.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/devpipe/ui/state.py src/devpipe/ui/actions.py src/devpipe/ui/services.py tests/ui/test_state.py tests/ui/test_actions.py
git commit -m "feat(ui): add state model for textual command palette layout"
```

### Task 2: Подготовить runtime event bridge для run screen

**Files:**
- Modify: `src/devpipe/app.py`
- Create: `src/devpipe/ui/run_session.py`
- Test: `tests/ui/test_run_screen.py`

- [ ] **Step 1: Write the failing tests for run events**

Покрыть:
- `run_started`
- `stage_started`
- streamed output chunks
- `stage_completed`
- `stage_failed`
- `run_finished`
- stage attempts в цикле `qa_stand -> developer`

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_run_screen.py -q`

Expected:
- FAIL, потому что UI пока не получает нормализованные runtime events

- [ ] **Step 3: Implement event bridge**

В `src/devpipe/app.py`:
- ввести единый callback/event API
- не давать UI читать internals runner’ов напрямую

В `src/devpipe/ui/run_session.py`:
- завернуть `OrchestratorApp.run()` в сервис
- преобразовывать runtime callbacks в typed UI messages
- сохранять stage attempt numbers для timeline

- [ ] **Step 4: Run tests to verify event bridge passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_run_screen.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/devpipe/app.py src/devpipe/ui/run_session.py tests/ui/test_run_screen.py
git commit -m "refactor(ui): add run event bridge for textual screens"
```

### Task 3: Поднять каркас `Textual` app и навигацию экранов

**Files:**
- Create: `src/devpipe/ui/app.py`
- Create: `src/devpipe/ui/screens/config_screen.py`
- Create: `src/devpipe/ui/screens/history_screen.py`
- Create: `src/devpipe/ui/screens/run_screen.py`
- Test: `tests/ui/test_config_screen.py`
- Test: `tests/ui/test_history_screen.py`
- Test: `tests/ui/test_run_screen.py`

- [ ] **Step 1: Write the failing tests for app shell**

Покрыть:
- старт на `config_screen`
- переход в `history_screen`
- переход в `run_screen`
- возврат в `config_screen` после завершения run
- базовые keyboard shortcuts

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_config_screen.py tests/ui/test_history_screen.py tests/ui/test_run_screen.py -q`

Expected:
- FAIL с отсутствующим `Textual` app

- [ ] **Step 3: Implement the app shell**

В `src/devpipe/ui/app.py`:
- создать `DevpipeTextualApp`
- подключить `UIState`
- централизовать screen routing
- держать единый `services` container

Ограничения:
- screens не читают YAML/history/git напрямую
- screens получают state и dispatch’ят actions

- [ ] **Step 4: Run tests to verify app shell passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_config_screen.py tests/ui/test_history_screen.py tests/ui/test_run_screen.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/devpipe/ui/app.py src/devpipe/ui/screens/config_screen.py src/devpipe/ui/screens/history_screen.py src/devpipe/ui/screens/run_screen.py tests/ui/test_config_screen.py tests/ui/test_history_screen.py tests/ui/test_run_screen.py
git commit -m "feat(ui): add textual app shell and screens"
```

### Task 4: Реализовать main config screen в формате `Command Palette + Summary Pane`

**Files:**
- Create: `src/devpipe/ui/widgets/nav_list.py`
- Create: `src/devpipe/ui/widgets/detail_panel.py`
- Create: `src/devpipe/ui/widgets/status_bar.py`
- Create: `src/devpipe/ui/widgets/input_field.py`
- Modify: `src/devpipe/ui/screens/config_screen.py`
- Modify: `src/devpipe/ui/services.py`
- Test: `tests/ui/test_config_screen.py`

- [ ] **Step 1: Write the failing tests for the approved config UX**

Покрыть:
- секции `Standard / Custom / Actions`
- стандартные поля:
  - `Profile`
  - `Task`
  - `Runner`
  - `Start Stage`
  - `Finish Stage`
- custom inputs как плоский список
- отсутствие `Task ID` в standard section
- inline-edit в detail pane
- status bar с contextual help и readiness
- disabled `Run Pipeline`, если обязательные поля невалидны

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_config_screen.py -q`

Expected:
- FAIL, потому что config screen пока не реализует утверждённый layout

- [ ] **Step 3: Implement navigation list and detail panel**

В `src/devpipe/ui/widgets/nav_list.py`:
- секции `Standard`, `Custom`, `Actions`
- визуальный focus state
- compact operator-console layout

В `src/devpipe/ui/widgets/detail_panel.py`:
- summary mode для текущего пункта
- inline-edit mode
- validation/errors inline

В `src/devpipe/ui/widgets/status_bar.py`:
- shortcuts слева
- contextual help по центру
- readiness/status справа

- [ ] **Step 4: Implement field editors**

В `src/devpipe/ui/widgets/input_field.py`:
- editors для `string`
- `int`
- `multi: true`
- `custom: false`
- `custom: true`

В `src/devpipe/ui/services.py`:
- подготовка field metadata для standard/custom sections

- [ ] **Step 5: Wire the approved screen behavior**

`ConfigScreen` должен:
- строить левую колонку по утверждённой структуре
- редактировать значения прямо в правой панели
- переключать focus между navigation и detail pane
- показывать readiness summary для `Run Pipeline`

- [ ] **Step 6: Run tests to verify config screen passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_config_screen.py -q`

Expected:
- PASS

- [ ] **Step 7: Commit**

```bash
git add src/devpipe/ui/widgets/nav_list.py src/devpipe/ui/widgets/detail_panel.py src/devpipe/ui/widgets/status_bar.py src/devpipe/ui/widgets/input_field.py src/devpipe/ui/screens/config_screen.py src/devpipe/ui/services.py tests/ui/test_config_screen.py
git commit -m "feat(ui): implement command palette config screen"
```

### Task 5: Перенести history в отдельный screen с preview и restore

**Files:**
- Create: `src/devpipe/ui/widgets/history_preview.py`
- Modify: `src/devpipe/ui/screens/history_screen.py`
- Modify: `src/devpipe/history.py`
- Test: `tests/ui/test_history_screen.py`

- [ ] **Step 1: Write the failing tests for history UX**

Покрыть:
- открытие `History` из action section
- список history entries активного profile
- preview справа
- restore записи обратно в form state
- корректную работу с multiple stage attempts

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_history_screen.py -q`

Expected:
- FAIL, потому что history screen пока не реализован

- [ ] **Step 3: Implement history screen**

В `src/devpipe/ui/widgets/history_preview.py`:
- preview widget в том же visual language

В `src/devpipe/history.py`:
- вернуть структуру, пригодную для `HistoryEntryState`
- сохранить profile-scoped loading API

В `HistoryScreen`:
- список слева
- preview справа
- restore/apply action

- [ ] **Step 4: Run tests to verify history screen passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_history_screen.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/devpipe/ui/widgets/history_preview.py src/devpipe/ui/screens/history_screen.py src/devpipe/history.py tests/ui/test_history_screen.py
git commit -m "feat(ui): add history screen with preview and restore"
```

### Task 6: Реализовать run screen с timeline слева и logs справа

**Files:**
- Create: `src/devpipe/ui/widgets/stage_timeline.py`
- Create: `src/devpipe/ui/widgets/log_viewer.py`
- Modify: `src/devpipe/ui/screens/run_screen.py`
- Modify: `src/devpipe/ui/run_session.py`
- Test: `tests/ui/test_run_screen.py`

- [ ] **Step 1: Write the failing tests for run screen UX**

Покрыть:
- timeline stage attempts
- отображение `developer #1`, `qa_stand #1`, `developer #2`
- log streaming в правую панель
- run metadata header
- нижнюю строку в run mode
- финальный summary и возврат к config screen

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_run_screen.py -q`

Expected:
- FAIL, потому что run screen пока не реализует утверждённый layout

- [ ] **Step 3: Implement the timeline and log widgets**

В `src/devpipe/ui/widgets/stage_timeline.py`:
- pending/active/done/failed/skipped states
- stage attempts numbering

В `src/devpipe/ui/widgets/log_viewer.py`:
- append-only API
- scroll support
- follow-tail mode

- [ ] **Step 4: Implement the run screen**

`RunScreen` должен:
- слева показывать timeline
- справа показывать run metadata и logs
- внизу показывать run-mode shortcuts и status
- принимать UI events из `run_session.py`

- [ ] **Step 5: Run tests to verify run screen passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/ui/test_run_screen.py -q`

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add src/devpipe/ui/widgets/stage_timeline.py src/devpipe/ui/widgets/log_viewer.py src/devpipe/ui/screens/run_screen.py src/devpipe/ui/run_session.py tests/ui/test_run_screen.py
git commit -m "feat(ui): implement textual run screen"
```

### Task 7: Перевести CLI на новый interactive frontend

**Files:**
- Modify: `src/devpipe/cli.py`
- Modify: `src/devpipe/tui.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests for CLI integration**

Покрыть:
- `devpipe` без subcommand запускает `Textual` app
- `devpipe run ...` остаётся headless mode
- interactive mode больше не использует `questionary`
- корректную деградацию без TTY

- [ ] **Step 2: Run tests to verify they fail**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -q`

Expected:
- FAIL, потому что CLI всё ещё использует legacy interactive flow

- [ ] **Step 3: Switch CLI wiring**

В `src/devpipe/cli.py`:
- убрать `_RunProgress`
- убрать raw terminal orchestration
- запускать `DevpipeTextualApp` как единственный interactive frontend

В `src/devpipe/tui.py`:
- сначала оставить compatibility shim
- после стабилизации удалить legacy implementation

- [ ] **Step 4: Run tests to verify CLI integration passes**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py tests/ui/test_config_screen.py tests/ui/test_history_screen.py tests/ui/test_run_screen.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add src/devpipe/cli.py src/devpipe/tui.py tests/test_cli.py
git commit -m "feat(cli): switch interactive frontend to textual"
```

### Task 8: Завершить миграцию и удалить legacy UI

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`
- Delete: `src/devpipe/tui.py`
- Test: `tests/test_cli.py`
- Test: `tests/ui/test_state.py`
- Test: `tests/ui/test_actions.py`
- Test: `tests/ui/test_config_screen.py`
- Test: `tests/ui/test_history_screen.py`
- Test: `tests/ui/test_run_screen.py`

- [ ] **Step 1: Add `Textual` dependency and remove old interactive dependency**

Изменения:
- добавить `textual`
- удалить `questionary`, если он больше не используется

- [ ] **Step 2: Document the approved UI**

README должен объяснить:
- layout `Command Palette + Summary Pane`
- секции `Standard / Custom / Actions`
- inline-edit справа
- run screen timeline + logs
- headless `devpipe run`

- [ ] **Step 3: Delete legacy TUI**

Удалить `src/devpipe/tui.py`, если после Task 7 он больше не нужен.

- [ ] **Step 4: Run full verification**

Run:
- `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py tests/ui/test_state.py tests/ui/test_actions.py tests/ui/test_config_screen.py tests/ui/test_history_screen.py tests/ui/test_run_screen.py -q`

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add README.md pyproject.toml tests/test_cli.py tests/ui
git rm src/devpipe/tui.py
git commit -m "feat(ui): migrate interactive frontend to approved textual design"
```

## Migration Notes

- Не переносить старый `questionary` UX один-в-один.
- Левая колонка должна оставаться стабильной по структуре; variability уходит только в `Custom`.
- `Task ID` и подобные поля должны появляться только как profile-driven custom inputs.
- Detail pane отвечает и за summary, и за inline-edit; не распылять эти роли по разным экранам.
- Status bar является частью контракта UI, а не декоративной полосой.
- `devpipe run ...` обязан остаться пригодным для CI и скриптов.
