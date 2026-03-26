# devpipe

devpipe — оркестратор AI-агентов для автоматизации цикла разработки. Он последовательно запускает шесть ролей, каждую из которых выполняет Codex или Claude по заранее заданному промпту.

```
architect → developer → test_developer → qa_local → release → qa_stand
```

Каждая роль получает на вход контекст предыдущих этапов, выполняет свою задачу и передаёт результат дальше. Оркестратор написан на Python, логика ролей — в промптах (`roles/*/prompt.md`).

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
- [mise](https://mise.jdx.dev/) (опционально, для управления версией Python)

### Установка

```bash
# С mise
mise install
mise run install

# Без mise
python -m venv .venv
.venv/bin/pip install -e .
```

### Запуск пайплайна

```bash
# Минимальный запуск (без Jira)
devpipe run \
  --task "Добавить новый метод оплаты" \
  --runner codex \
  --stand u1 \
  --dataset s4-3ds \
  --service acquiring

# С задачей из Jira
devpipe run \
  --task-id MRC-123 \
  --task "Добавить новый метод оплаты" \
  --runner codex \
  --stand u1 \
  --dataset s4-3ds \
  --service acquiring
```

> После `pip install -e .` команда `devpipe` доступна глобально. Без установки: `.venv/bin/python -m devpipe`.

## Частичный запуск

Можно запустить только часть пайплайна — например, остановиться после разработки или начать с тестирования.

```bash
# Только архитектура и разработка
devpipe run --task "..." --runner codex --last-role developer

# Только тесты
devpipe run --task "..." --runner codex \
  --first-role test_developer --last-role test_developer

# От qa_local до конца
devpipe run --task "..." --runner codex \
  --first-role qa_local \
  --stand u1 --dataset s4-3ds --service acquiring
```

Namespace (`--namespace` или `config/namespace-map.yaml`) нужен только если в диапазоне присутствует `release` или `qa_stand`.

## Все флаги

| Флаг | Обязательный | По умолчанию | Описание |
|------|:---:|---|---|
| `--task` | да | — | Текст задачи |
| `--runner` | да | — | `codex` или `claude` |
| `--task-id` | нет | — | ID задачи в Jira; если указан — загружается контекст |
| `--stand` | нет | — | Стенд: `u1`, `u1-1`, `u1-4` |
| `--dataset` | нет | — | Датасет для стенда |
| `--service` | нет | `acquiring` | Имя сервиса |
| `--namespace` | нет | — | Kubernetes namespace; если не указан — берётся из `config/namespace-map.yaml` |
| `--deploy-branch` | нет | — | Ветка для деплоя |
| `--tag` | нет | — | Теги через запятую (например `go`) |
| `--first-role` | нет | `architect` | С какой роли начать |
| `--last-role` | нет | `qa_stand` | На какой роли остановиться |

## Структура проекта

```
devpipe/
├── roles/                  # Определения ролей
│   └── <role>/
│       ├── prompt.md       # Инструкции для AI
│       ├── role.yaml       # Метаданные роли (runner, retry_limit, inputs/outputs)
│       └── output.schema.json  # JSON-схема ожидаемого вывода
├── config/
│   ├── runners.yaml        # Конфигурация runners (команда, timeout)
│   └── namespace-map.yaml  # Маппинг service/stand → Kubernetes namespace
├── tags/                   # Правила для конкретных технологий
│   └── go/                 # Go-специфичные правила для developer и test_developer
├── src/devpipe/            # Исходный код оркестратора
│   ├── cli.py              # Точка входа CLI
│   ├── app.py              # Основная логика, RunConfig
│   ├── runtime/            # State machine, события, retry-политика
│   ├── roles/              # Загрузка ролей, сборка промптов
│   ├── runners/            # Адаптеры Codex и Claude
│   ├── integrations/       # Jira, GitHub, Kubernetes, Git
│   └── storage/            # Логирование и артефакты
├── tests/                  # Тесты
└── runs/                   # Артефакты запусков (в .gitignore)
```

## Артефакты запуска

Каждый запуск сохраняет данные в `runs/<run_id>/`:

- `events.jsonl` — полный лог событий
- `summary.json` — итоговый статус и метаданные
- `<role>/` — вывод каждой роли

## Конфигурация

### Namespace mapping (`config/namespace-map.yaml`)

Позволяет не указывать `--namespace` явно:

```yaml
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

### Теги

Файлы в `tags/<tag>/` добавляют правила к промптам конкретных ролей. Например, `tags/go/DEVELOPER_RULES.md` подключается автоматически для Go-проектов:

```bash
devpipe run --task "..." --runner codex --tag go
```

Кастомные правила для проекта можно положить в `.devpipe/`.

## Утилиты

```bash
# Список доступных ролей
devpipe inspect --roles-dir roles

# Через mise
mise run roles
mise run test
```

## Деградированные режимы

- **Без `--task-id`** — Jira не читается, пайплайн работает только на тексте задачи.
- **Jira недоступна** — контекст пропускается, пайплайн продолжается.
- **Нет namespace mapping** — запуск падает только если нужны `release` или `qa_stand`.
- **GitHub workflow упал** — стоп после стадии `release`.
- **Kubernetes timeout** — стоп перед `qa_stand`.
