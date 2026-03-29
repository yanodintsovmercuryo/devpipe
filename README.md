# devpipe

AI-агент оркестратор для автоматизации цикла разработки. Запускает шесть ролей последовательно, каждую выполняет Codex или Claude по заданным промптам и правилам.

```
architect → developer → test_developer → qa_local → release → qa_stand
```

---

## Установка

```bash
mise install        # устанавливает python 3.13
mise run install    # создаёт .venv и устанавливает зависимости
```

Без mise:
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
```

---

## Запуск

```bash
devpipe          # интерактивное TUI — основной режим
devpipe run ...  # без TUI, все параметры флагами — для скриптов и CI
```

---

## Интерактивное меню

```
┌─ devpipe ─────────────────────────────────────┐
│  task          ← required                     │
│  task-id       MRC-123        (из ветки git)  │
│  runner        codex                          │
│  target-branch u1                             │
│  service       acquiring                      │
│  namespace     auto                           │
│  tags          acquiring-service, go          │
│    dataset     s4-3ds                         │
│  roles         architect → qa_stand           │
└───────────────────────────────────────────────┘
```

- **task-id** — подставляется автоматически из ветки (`MRC-123-my-feature` → `MRC-123`). Если указан — загружается контекст из Jira. Можно очистить чтобы пропустить Jira.
- **target-branch** — стенд для деплоя. Если не указан — пайплайн останавливается на `qa_local`.
- **tags** — список с множественным выбором. Параметры активных тегов появляются отдельными пунктами меню.
- **first role / last role** — диапазон ограничен, невалидный выбрать нельзя.
- **▶ Run** — появляется только когда `task` заполнен.

---

## Частичный запуск

Например, только разработка без деплоя:

```
Set last role → developer
```

Или через CLI:
```bash
devpipe run --task "..." --runner codex --last-role developer
```

---

## Настройка проекта (.devpipe/)

Создай `.devpipe/` в корне **рабочего репозитория** (не в devpipe). Именно оттуда devpipe читает конфигурацию при запуске.

### config.yaml

```yaml
defaults:
  runner: codex
  service: my-service
  tags:
    - my-service          # проектный тег
    - go                  # builtin тег

available:
  target_branch:          # список для выбора в TUI
    - u1
    - u1-1
  namespace:
    - my-service-u1
    - my-service-u1-1
```

- `defaults` — начальные значения в TUI
- `available` — если список заполнен, в TUI будет выпадашка; если пуст — свободный ввод

### tags/

Кастомные теги проекта. Та же структура что и builtin `tags/` в этом репозитории.

```
.devpipe/
  config.yaml
  tags/
    my-service/
      architect/
        rules.md
      developer/
        rules.md
      test_developer/
        rules.md
      qa_local/
        rules.md
      release/
        rules.md
      qa_stand/
        rules.md
        params.yaml       # параметры нужные qa_stand (опционально)
```

Каждый файл `rules.md` дописывается к промпту соответствующей роли когда тег активен.

---

## Теги

### Как работают

При запуске роли devpipe собирает промпт так:

```
<базовый промпт роли>

## Tag Rules: my-service
<содержимое .devpipe/tags/my-service/<role>/rules.md>

## Tag Rules: go
<содержимое tags/go/<role>/rules.md>
```

Порядок поиска `rules.md` для тега:
1. `.devpipe/tags/<tag>/<role>/rules.md` — кастомные теги проекта
2. `tags/<tag>/<role>/rules.md` — builtin теги devpipe

### params.yaml — параметры для роли

Если роли нужны входные данные (например `dataset` для qa_stand), объяви их в `params.yaml` рядом с `rules.md`:

```yaml
# .devpipe/tags/my-service/qa_stand/params.yaml
params:
  - key: dataset
    description: Test dataset
    required: true
    available:
      - s4-3ds
      - s4-no3ds
```

При запуске:
- TUI покажет `Set dataset` как отдельный пункт меню
- Выбранное значение попадёт в `release_context` который AI видит в промпте
- В `rules.md` можно ссылаться на него: `{release_context.dataset}`

### Builtin теги

| Тег | Роли |
|-----|------|
| `go` | `developer`, `test_developer` |

---

## Пример: acquiring

```
acquiring-repo/
  .devpipe/
    config.yaml
    tags/
      acquiring-service/
        architect/rules.md
        developer/rules.md
        test_developer/rules.md
        qa_local/rules.md
        release/rules.md
        qa_stand/
          rules.md        ← инструкции по pw-exchange-buy
          params.yaml     ← dataset param
```

`config.yaml`:
```yaml
defaults:
  runner: codex
  service: acquiring
  tags:
    - acquiring-service
    - go

available:
  target_branch:
    - u1
    - u1-1
    - u1-4
  namespace:
    - acquiring-u1
    - acquiring-u1-1
    - acquiring-u1-4
```

---

## devpipe run (без TUI)

Для скриптов и CI — все параметры передаются флагами напрямую:

```bash
devpipe run \
  --task "Описание задачи" \
  --task-id MRC-123 \
  --runner codex \
  --target-branch u1 \
  --service acquiring \
  --tag acquiring-service,go \
  --param dataset=s4-3ds \
  --last-role qa_stand
```

| Флаг | Описание |
|------|---------|
| `--task` | Текст задачи (обязательный) |
| `--task-id` | ID в Jira (опционально, включает загрузку контекста) |
| `--runner` | `codex` или `claude` |
| `--target-branch` | Стенд / ветка деплоя |
| `--service` | Имя сервиса |
| `--namespace` | Kubernetes namespace for the `release` stage |
| `--tag` | Теги через запятую |
| `--param` | Параметр тега: `key=value`, можно несколько |
| `--first-role` | С какой роли начать |
| `--last-role` | На какой остановиться |

---

## Структура репозитория

```
devpipe/
├── roles/              # базовые промпты и схемы вывода для каждой роли
│   └── <role>/
│       ├── prompt.md
│       ├── role.yaml
│       └── output.schema.json
├── tags/               # builtin теги (универсальные, не проектные)
│   └── go/
│       ├── developer/rules.md
│       └── test_developer/rules.md
├── config/
│   └── runners.yaml        # настройки runners: команда, timeout, model/effort mapping
└── src/devpipe/
    ├── cli.py
    ├── tui.py              # интерактивное меню
    ├── app.py              # RunConfig, OrchestratorApp
    ├── tags.py             # загрузка тегов и params.yaml
    ├── project_config.py   # загрузка .devpipe/config.yaml
    ├── runtime/            # state machine, события, retry
    ├── roles/              # загрузка ролей, сборка промптов
    ├── runners/            # Codex и Claude адаптеры
    ├── integrations/       # Jira, GitHub, Kubernetes, Git
    └── storage/            # логи и артефакты запусков
```

---

## Pipeline Profiles (новый способ)

`devpipe` теперь использует **profile-driven** архитектуру: вместо жёстко зашитых ролей `STAGE_ORDER` пайплайн описывается декларативно в YAML-файлах.

### Структура профиля

Профиль — это директория `.devpipe/profiles/<profile_name>/` (проектный) или `src/devpipe/profiles/<profile_name>/` (встроенный в репозиторий). Обязательный файл: `pipeline.yml`.

```
.devpipe/
  profiles/
    my-profile/
      pipeline.yml
      agents/
        architect/
          prompt.md
          output.schema.json
        developer/
          ...
```

### pipeline.yml DSL

**Минимальный контракт:**

```yaml
version: 1
name: my-profile

defaults:
  runner: auto
  model: middle
  effort: middle

inputs:
  <input_key>:
    type: string | int | array | object | bool
    required: true | false
    default: <scalar-or-list>
    values: [<enum-values>]        # если custom=false
    multi: true | false            # для arrays
    custom: true | false           # разрешать произвольные значения

stages:
  <stage_name>:
    runner: codex | claude | auto
    model: low | middle | high | auto
    effort: low | middle | high | extra | auto
    retry_limit: <int>
    agent:
      prompt: agents/<stage_name>/prompt.md
      output_schema: agents/<stage_name>/output.schema.json
    in:
      <target>: <source_path>
      ...
    out:
      <field>:
        type: string | int | bool | object | array
        description: optional
      ...

routing:
  start_stage: <stage_name>
  by_stage:
    <stage_name>:
      next_stages:
        - stage: <next_stage_name>
          all:      # все условия должны совпасть
            - field: <field_ref>
              op: eq | neq | gt | gte | lt | lte | in | contains
              value: <value>
          any:      # хотя бы одно условие
            - ...
          default: true   # правило по умолчанию (первое)
```

### Выбор профиля

1. **CLI**: `devpipe run --profile <name> ...`
2. **TUI**: В Configuration Screen появится поле `Profile`. Выбор профиля перезагружает список Stages и Inputs.
3. **Проектный конфиг**: `.devpipe/config.yaml` → `defaults.profile: <name>`

Если профиль не указан — используется builtin `default` (если есть) или fallback на legacy `STAGE_ORDER`.

### Входы (`inputs`)

Определяют поля, которые пользователь заполняет в конфигурации:
- `type` — тип значения.
- `required` — если true, поле должно быть заполнено.
- `default` — значение по умолчанию.
- `values` — список разрешённых значений (только если `custom: false`).
- `multi: true` — поле принимает список (для `type: array`).
- `custom: true` — любое значение указанного типа (обход `values`).

Пример:

```yaml
inputs:
  environment:
    type: string
    required: false
    default: "staging"
    values: ["development", "staging", "production"]
    custom: false
  components:
    type: array
    required: false
    default: []
    multi: true
    custom: true
```

### Стадии (`stages`)

Каждая стадия описывает конфигурацию агента:
- `runner`, `model`, `effort`, `retry_limit`.
- `agent.prompt` и `agent.output_schema` — файлы внутри профиля.
- `in.bindings` — откуда брать входные данные для этой стадии.
- `out.fields` — какие поля возвращает агент (для валидации и последующих bindings).

**Bindings** (`in`): маппинг целевых имен на источники:

- `input.<key>` — глобальный вход профиля.
- `stage.<stage_name>.out.<field>` — выход другой стадии.
- `context.shared` — общий контекст (например, дата создания).
- `runtime.git.current_branch` — текущая ветка.
- `integration.jira.issue` — данные из Jira (если адаптер есть).

Использование точечной нотации в целевом ключе создаёт вложенные структуры:

```yaml
in:
  release_inputs.branch: runtime.git.current_branch
  release_inputs.target_branch: input.target_branch
```
→ в контексте стадии будет `release_inputs: { branch: "...", target_branch: "..." }`.

**Outputs** (`out`): описывает возвращаемые поля агента:

```yaml
out:
  build_id:
    type: string
    description: "ID сборки"
  artifacts:
    type: object
```

### Маршрутизация (`routing`)

Определяет, как пайплайн переходит между стадиями:
- `start_stage` — с какой стадии начинать.
- `by_stage.<stage>.next_stages` — список правил, проверяемых сверху вниз. Первое совпавшее правило выбирает следующую стадию.

Правило содержит:
- `stage` — следующая стадия (`completed` или `failed` — специальные финальные состояния).
- `all` или `any` — условия (можно не указывать для `default: true`).
- `default: true` — правило по умолчанию (если ни одно не сработало).

**Операторы:** `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in` (значение в списке), `contains` (подстрока или элемент списка).

**Поля условий** (`field`):
- `input.<key>` — вход профиля.
- `in.<key>` — синоним `input.`.
- `out.<field>` — выход текущей стадии.
- `stage.<stage>.out.<field>` — выход конкретной стадии.
- `context.<key>` — общий контекст.
- `runtime.<key>` — runtime-информация.
- `integration.<key>` — данные интеграций.

### Пример профиля: acquiring-service

См. `examples/acquiring/.devpipe/profiles/acquiring-service/pipeline.yml`. Профиль демонстрирует:
- Тиражированные входы с `values`, `multi`, `custom`.
- Вложенные bindings `release_inputs.branch`.
- Условную маршрутизацию `all` / `any`.
- Линейный этап и возврат на доработку (`quality_gate → builder`).

### Builtin профили

Встроенные профили находятся в `src/devpipe/profiles/`. Профиль `default` используется, если проект не имеет своего.

---

## Примечание по миграции

Старая система жёстко зашитых ролей (`roles/`, `tags/`, `STAGE_ORDER`) сохранена для совместимости, но новая рекомендуется. При использовании профиля:
- TUI строит конфигурацию из `inputs` профиля.
- Стадии берутся из `stages`.
- Переходы вычисляются по `routing` (не по `on_success/on_failure`).
- История сохраняется отдельно на каждый профиль и включает цепочку попыток (`stage_attempts`).

