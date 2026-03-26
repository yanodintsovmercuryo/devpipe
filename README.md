# devpipe

devpipe — оркестратор AI-агентов для автоматизации цикла разработки. Последовательно запускает шесть ролей, каждую из которых выполняет Codex или Claude по заранее заданному промпту.

```
architect → developer → test_developer → qa_local → release → qa_stand
```

## Что делает каждая роль

| Роль | Задача |
|------|--------|
| `architect` | Анализирует задачу, составляет план реализации |
| `developer` | Реализует код по плану архитектора |
| `test_developer` | Пишет тесты для изменений |
| `qa_local` | Проверяет корректность локально |
| `release` | Готовит и выполняет деплой |
| `qa_stand` | Проверяет задеплоенные изменения на стенде |

## Быстрый старт

### Требования

- Python 3.9+
- [Codex CLI](https://github.com/openai/codex) и/или [Claude CLI](https://claude.ai/code)
- [mise](https://mise.jdx.dev/) (опционально)

### Установка

```bash
# С mise
mise install
mise run install

# Без mise
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

### Запуск

```bash
# Интерактивный TUI (рекомендуется)
devpipe

# Напрямую через CLI
devpipe run --task "Добавить новый метод оплаты" --runner codex
```

## Интерактивный TUI

`devpipe` без аргументов открывает меню конфигурации:

```
┌─ devpipe ───────────────────────────────────────┐
│  task          (empty)  ← required              │
│  task-id       MRC-123                          │
│  runner        codex                            │
│  target-branch none → last role: qa_local       │
│  service       acquiring                        │
│  namespace     auto                             │
│  tags          go, exchange_buy                 │
│    dataset     s4-3ds          [exchange_buy]   │
│  roles         architect → qa_local             │
└─────────────────────────────────────────────────┘

> Set task
  Set task ID
  Set runner
  Set target branch
  ...
  ▶  Run
```

- `task-id` предзаполняется из текущей ветки git (`MRC-123-feature` → `MRC-123`)
- `target-branch` пустой → последняя роль автоматически `qa_local`; заполнен → `qa_stand`
- Теги с параметрами добавляют свои пункты в меню (например `Set dataset  [exchange_buy]`)
- Выбор `first role` / `last role` ограничен — невалидный диапазон выбрать нельзя
- `▶  Run` появляется только когда `task` заполнен

## CLI (скриптовый режим)

```bash
devpipe run \
  --task "Добавить новый метод оплаты" \
  --runner codex \
  --target-branch u1 \
  --service acquiring \
  --namespace acquiring-u1 \
  --tag go,exchange_buy \
  --param dataset=s4-3ds
```

### Все флаги

| Флаг | Обязательный | Описание |
|------|:---:|---------|
| `--task` | да | Текст задачи |
| `--runner` | да | `codex` или `claude` |
| `--task-id` | нет | ID задачи в Jira; если указан — загружается контекст |
| `--target-branch` | нет | Целевая ветка / стенд для деплоя |
| `--service` | нет | Имя сервиса (default: `acquiring`) |
| `--namespace` | нет | Kubernetes namespace (иначе из `namespace-map.yaml`) |
| `--tag` | нет | Теги через запятую (например `go,exchange_buy`) |
| `--param` | нет | Параметр тега в формате `key=value`, можно несколько |
| `--first-role` | нет | С какой роли начать |
| `--last-role` | нет | На какой роли остановиться |

## Частичный запуск

```bash
# Только архитектура и разработка (namespace не нужен)
devpipe run --task "..." --runner codex --last-role developer

# Только тесты
devpipe run --task "..." --runner codex \
  --first-role test_developer --last-role test_developer
```

`target-branch` пустой → `last-role` по умолчанию `qa_local`. Namespace нужен только если в диапазоне есть `release` или `qa_stand`.

## Теги

Тег делает две вещи:

1. **Добавляет правила к промптам ролей** — файлы вида `DEVELOPER_RULES.md`, `QA_STAND_RULES.md` и т.д. в директории тега автоматически дописываются к промпту соответствующей роли когда тег активен.

2. **Объявляет входные параметры** — в `tag.yaml` тег описывает какие значения ему нужны (например `dataset`). Эти значения появляются в TUI как отдельные пункты меню, а при запуске попадают в `release_context` — и AI видит их в своём промпте.

### Как это работает на примере `exchange_buy`

Тег объявляет параметр `dataset` в `tag.yaml`. При запуске значение `s4-3ds` попадает в контекст роли `qa_stand`:

```
Context: {
  ...
  "release_context": {
    "target_branch": "u1",
    "dataset": "s4-3ds",
    ...
  }
}
```

В `QA_STAND_RULES.md` написано что с этим делать:

```markdown
Run the `/pw-exchange-buy` skill:

    /pw-exchange-buy \
      --stand {release_context.target_branch} \
      --dataset {release_context.dataset}
```

AI читает правила, берёт значения из контекста и выполняет сценарий.

### Встроенные теги

| Тег | Правила для ролей | Параметры |
|-----|-------------------|-----------|
| `go` | `DEVELOPER_RULES.md`, `TEST_DEVELOPER_RULES.md` | — |
| `exchange_buy` | `QA_STAND_RULES.md` | `dataset` |

### Структура тега

```
tags/
  my_tag/
    tag.yaml                # описание тега (опционально)
    QA_STAND_RULES.md       # правила для qa_stand (опционально)
    QA_STAND_PARAMS.yaml    # параметры для qa_stand (опционально)
    DEVELOPER_RULES.md      # правила для developer (опционально)
    DEVELOPER_PARAMS.yaml   # параметры для developer (опционально)
    ...
```

Каждая роль может иметь свой `*_RULES.md` и свой `*_PARAMS.yaml`. Правила дописываются к промпту роли. Параметры из `*_PARAMS.yaml` появляются в TUI и попадают в `release_context`.

**`QA_STAND_PARAMS.yaml`:**
```yaml
params:
  - key: my_param
    description: Описание параметра
    required: true
    available:
      - value1
      - value2
```

Если параметры не нужны — файл можно не создавать.

### Кастомные правила проекта

Файлы в `.devpipe/` добавляются к промптам ролей независимо от тегов:

```
.devpipe/
  DEVELOPER_RULES.md
  QA_STAND_RULES.md
  ...
```

## Конфигурация проекта

Создай `.devpipe/config.yaml` в корне рабочего репозитория:

```yaml
defaults:
  runner: codex
  service: acquiring
  tags:
    - go
    - exchange_buy

available:
  target_branch:
    - u1
    - u1-1
    - u1-4
  namespace:
    - acquiring-u1
    - acquiring-u1-1
    - acquiring-u1-4

tag_params:
  exchange_buy:
    defaults:
      dataset: s4-3ds
    available:
      dataset:
        - s4-3ds
        - s4-no3ds
        - s4-3ds-recurrent
```

- `defaults` — начальные значения в TUI
- `available` — списки для выбора в TUI (для `target_branch`, `namespace`); при пустом списке — свободный ввод
- `tag_params` — переопределяет defaults/available для параметров конкретных тегов

Пример готового конфига для acquiring: [`acquiring.devpipe.yaml`](acquiring.devpipe.yaml).

## Конфигурация оркестратора

### Namespace mapping (`config/namespace-map.yaml`)

```yaml
services:
  acquiring:
    u1: acquiring-u1
    u1-1: acquiring-u1-1
```

### Runners (`config/runners.yaml`)

```yaml
runners:
  codex:
    command: ["codex"]
    timeout: 300
  claude:
    command: ["claude"]
    timeout: 300
```

## Структура проекта

```
devpipe/
├── roles/                  # Определения ролей
│   └── <role>/
│       ├── prompt.md       # Инструкции для AI
│       ├── role.yaml       # Метаданные (runner, retry_limit, inputs/outputs)
│       └── output.schema.json
├── tags/                   # Теги
│   └── <tag>/
│       ├── tag.yaml        # Параметры тега
│       └── *_RULES.md      # Правила для ролей
├── config/                 # Конфигурация оркестратора
├── src/devpipe/            # Исходный код
│   ├── cli.py              # CLI точка входа
│   ├── tui.py              # Интерактивный TUI
│   ├── app.py              # RunConfig и OrchestratorApp
│   ├── tags.py             # Загрузка tag.yaml
│   ├── project_config.py   # Загрузка .devpipe/config.yaml
│   ├── runtime/            # State machine, события, retry
│   ├── roles/              # Загрузка ролей, сборка промптов
│   ├── runners/            # Адаптеры Codex и Claude
│   ├── integrations/       # Jira, GitHub, Kubernetes, Git
│   └── storage/            # Логи и артефакты
└── runs/                   # Артефакты запусков (в .gitignore)
```

## Артефакты запуска

Каждый запуск сохраняется в `runs/<run_id>/`:
- `events.jsonl` — полный лог событий
- `summary.json` — итоговый статус
- `<role>/` — вывод каждой роли

## Деградированные режимы

- **Без `--task-id`** — Jira не читается, пайплайн работает только на тексте задачи
- **Jira недоступна** — контекст пропускается, пайплайн продолжается
- **Нет namespace** — падает только если нужны `release` или `qa_stand`
- **GitHub workflow упал** — стоп после `release`
- **Kubernetes timeout** — стоп перед `qa_stand`

## Утилиты

```bash
devpipe inspect --roles-dir roles   # список ролей
mise run test                       # тесты
```
