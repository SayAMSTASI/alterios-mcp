# alterios-mcp

`alterios-mcp` - MCP-сервер для чтения, проектирования, управляемой записи и
проверки проектов Alterios/LIMS из Codex и других MCP-клиентов.

Сервер рассчитан на несколько экземпляров Alterios и множество проектов внутри
каждого экземпляра. Основной рабочий контур: инвентаризация -> постановка ->
dry-run -> проверенный `plan_id` -> запись -> API/UI readback -> приватный отчёт
о результате.

Текущая версия: **0.2.3**. Публичный registry содержит **108 MCP tools**:
`live` - 81, `discovery` - 55, `admin` - 106, `full` - 108.

## Основные возможности

- проекты, типы материалов, поля, контент и файлы;
- представления, связи, view entities, поля, фильтры и форматы отображения;
- формы, вкладки, строки, ячейки, listeners и действия;
- Google Fonts Icons с проектным registry и загрузкой в файловый менеджер;
- web/cron/manual/event/library/diagram scripts и их аргументы;
- BPMN, процессы, задачи, `camunda:formKey` и проверка side effects;
- Project Database reports, Stimulsoft templates и printable render/PDF check;
- users, user groups, roles и destructive operations через отдельные gates;
- сценарные операции для модулей материалов, отчётных вкладок и процессов;
- private Gitea work items, agent handoffs и stage labels;
- cached project health, write plans, journal, replay smoke и runtime fingerprint.

Полная матрица: [docs/alterios-method-coverage.md](docs/alterios-method-coverage.md).

## Быстрый старт

### 1. Установка готового релиза

Требуется Python 3.11 или новее.

```powershell
$manager = "$env:LOCALAPPDATA\alterios-mcp\manage_release.ps1"
New-Item (Split-Path $manager) -ItemType Directory -Force | Out-Null
Invoke-WebRequest `
  "https://github.com/SayAMSTASI/alterios-mcp/releases/latest/download/manage_release.ps1" `
  -OutFile $manager
& $manager -Action Install -DotenvPath "C:\path\to\private\alterios.env"
```

Менеджер сам скачивает wheel последнего GitHub Release, проверяет wheel и свою
обновлённую копию по `SHA256SUMS.txt`, создаёт окружение, устанавливает MCP и
запускает doctor и release smoke. Он сохраняется в постоянном каталоге
пользователя.

Последующие обновления выполняются одной командой:

```powershell
& "$env:LOCALAPPDATA\alterios-mcp\manage_release.ps1" -Action Update
```

Перед обновлением закройте Codex или другой MCP-клиент. Если это неудобно,
добавьте `-StopRunningMcp`: менеджер остановит только процессы из своей `.venv`.
Предыдущий release wheel сохраняется и используется для автоматического
rollback, если doctor или release smoke после обновления не пройдут.

Проверить наличие версии и получить варианты исправления можно без записи:

```powershell
& "$env:LOCALAPPDATA\alterios-mcp\manage_release.ps1" -Action Check
& "$env:LOCALAPPDATA\alterios-mcp\manage_release.ps1" -Action Solutions
```

Для разработки из исходного кода:

```powershell
git clone https://github.com/SayAMSTASI/alterios-mcp.git
cd alterios-mcp
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Для фиксированной версии или автономной установки можно передать менеджеру URL
или локальный путь к wheel. После любой операции перезапустите MCP-клиент:
работающий процесс не перечитывает пакет и registry автоматически.

```powershell
.\manage_release.ps1 -Action Update `
  -Package "C:\packages\alterios_mcp-0.2.3-py3-none-any.whl" `
  -ExpectedSha256 "<sha256>" `
  -DotenvPath "C:\path\to\private\alterios.env"
```

### 1.1. Предложения по устранению проблем

Команда `alterios-suggest-fixes` запускает read-only диагностику и возвращает
для каждой ошибки несколько вариантов решения: рекомендуемый путь,
альтернативу, готовую команду, уровень риска и необходимость перезапуска.

```powershell
& "$env:LOCALAPPDATA\alterios-mcp\venv\Scripts\alterios-suggest-fixes.exe" `
  --require-config --processes
```

### 2. Приватная конфигурация

Скопируйте структуру из `.env.example` в файл **вне репозитория**. Не коммитьте
токены, cookie, реальные адреса и идентификаторы проектов.

```dotenv
ALTERIOS_PROFILE=primary
ALTERIOS_PROFILES=primary,secondary

ALTERIOS_PRIMARY_BASE_URL=https://alterios-primary.example.local
ALTERIOS_PRIMARY_API_TOKEN=replace-me
ALTERIOS_PRIMARY_AUTH_HEADER=x-api-key
ALTERIOS_PRIMARY_AUTH_SCHEME=
ALTERIOS_PRIMARY_TIMEOUT_SECONDS=20

ALTERIOS_SECONDARY_BASE_URL=https://alterios-secondary.example.local
ALTERIOS_SECONDARY_API_TOKEN=replace-me
ALTERIOS_SECONDARY_AUTH_HEADER=Authorization
ALTERIOS_SECONDARY_AUTH_SCHEME=Bearer
ALTERIOS_SECONDARY_TIMEOUT_SECONDS=20

ALTERIOS_MCP_TOOL_PROFILE=live
ALTERIOS_MCP_ALLOW_WRITE=0
ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=0
ALTERIOS_MCP_REQUIRED_AGENT_ROLES=analyst,implementer,verifier
```

Один профиль описывает один экземпляр Alterios. Проект для каждой операции
передаётся явным `project_id`; default project в профиле используется только
как локальное удобство, а не как скрытая маршрутизация записи.

### 3. Подключение к Codex

Используйте установленный console entry point. Не создавайте несколько
одинаковых записей `mcp_servers.alterios`, иначе клиент запустит несколько
экземпляров сервера.

```toml
[mcp_servers.alterios]
command = "C:\\Users\\<user>\\AppData\\Local\\alterios-mcp\\venv\\Scripts\\alterios-mcp.exe"
args = []
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\path\\to\\private\\alterios.env"
ALTERIOS_MCP_TOOL_PROFILE = "live"
```

Локальная диагностическая команда:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\path\to\private\alterios.env"
& "$env:LOCALAPPDATA\alterios-mcp\venv\Scripts\alterios-mcp.exe"
```

Для MCP config не используйте `python -m alterios_mcp.server`: console script
является единственной рекомендуемой точкой запуска. Python module entry point
оставлен только для совместимости и диагностики.

### 4. Проверка после установки

```powershell
& "$env:LOCALAPPDATA\alterios-mcp\venv\Scripts\alterios-doctor.exe" --require-config --json
& "$env:LOCALAPPDATA\alterios-mcp\venv\Scripts\alterios-profile-smoke.exe" --json
& "$env:LOCALAPPDATA\alterios-mcp\venv\Scripts\alterios-replay-smoke.exe" --json
```

Перед записью в конкретный проект:

```powershell
.\.venv\Scripts\alterios-project-health.exe `
  --profile <profile> `
  --project-id <project-id> `
  --refresh `
  --json `
  --pretty
```

## Профили MCP tools

| Профиль | Tools | Назначение |
|---|---:|---|
| `live` | 81 | Основной профиль: health, scenarios, typed writes и проверка результата |
| `discovery` | 55 | Read-only исследование, inventory и validators |
| `admin` | 106 | Администрирование, security и controlled destructive operations |
| `full` | 108 | Разработка MCP и исследование неизвестных routes |

Профиль выбирается до запуска процесса через `ALTERIOS_MCP_TOOL_PROFILE`.
Для обычных задач используйте `live`. `full` не является режимом повышенного
качества и не нужен для повседневной работы.

Подробнее: [docs/mcp-tool-profiles.md](docs/mcp-tool-profiles.md).

## Управляемая запись

Запись по умолчанию выключена. Без выполнения gate-условий tools возвращают
план или audit и не отправляют изменяющий запрос.

Обычная запись требует:

1. Явные `profile` и `project_id`.
2. Успешный `alterios_live_task_preflight`.
3. Dry-run и проверенный `plan_id`, если сценарий поддерживает планы.
4. `ALTERIOS_MCP_ALLOW_WRITE=1` в окружении MCP-процесса.
5. Apply с теми же аргументами и `plan_id`.
6. API readback и UI/render check для пользовательской поверхности.
7. Запись результата в private Gitea, без публикации project evidence в GitHub.

Security/delete дополнительно требуют:

```dotenv
ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1
```

и `allow_destructive=true` в tool call. Перед неизвестным route используйте
`alterios_write_safety_preflight`.

Подробно: [docs/controlled-writes.md](docs/controlled-writes.md).

## Сценарные tools

### Модуль материала

`alterios_create_material_module` создаёт согласованный набор:

- тип материала и поля;
- experimental view, entity и view fields;
- list/add/edit/detail forms;
- группу меню и project-local icons;
- dry-run plan и readback.

### Вкладка отчёта

`alterios_create_report_tab` связывает source view, Project Database report и
form tab, проверяет `openId`/`dataId`, template layout и readback. Печатный
результат проверяется `alterios_validate_printable_render`.
При apply без явного `template` сценарий берет точный шаблон из сохраненного
dry-run плана; передавать сгенерированный Stimulsoft JSON повторно вручную не нужно.

`alterios_diagnose_report_viewer` раздельно проверяет source view, тип и шаблон
Stimulsoft, layout, привязку report-ячейки формы, printable PDF и evidence
браузерного viewer-контейнера. Отсутствие browser evidence возвращается как
явное предупреждение, а не маскируется успешным API readback.

### Процесс

`alterios_create_process_flow` связывает task form, scripts, BPMN XML,
`camunda:formKey`, запуск процесса и task/process readback.

### Массовые операции

- `alterios_bulk_update_selected_content_fields` - обновление полей выбранных записей;
- `alterios_fast_live_bulk_manual_script` - manual script по выбранным ID;
- `alterios_fast_live_bulk_process` - BPMN process по выбранным ID;
- `alterios_fast_live_bulk_delete` - destructive delete только в `admin/full`.

## UX-контракт

Формы и сценарные tools проверяются не только по JSON-схеме, но и по
пользовательским правилам:

- представления по умолчанию создаются в experimental mode;
- для add/edit/list/detail создаются отдельные формы с понятными заголовками;
- формы используют фильтр по текущему полю/`openId`, когда это требуется связью;
- технические и неинформативные столбцы скрываются;
- footnote используется только для поля даты;
- действия элемента оформляются project-local icon + tooltip;
- три и более вторичных действий группируются в меню;
- табличный заголовок центрирован и выделен bold;
- нетабличная ячейка не получает лишний заголовок;
- `iconId` всегда относится к файлу текущего проекта.

Проверка: `alterios_validate_form_contract`. Источник правил:
[docs/ux-contract.md](docs/ux-contract.md) и
[docs/ux-contract.json](docs/ux-contract.json).
Матрица происхождения правил из skills и граница между блокирующими,
evidence-gated и рекомендательными требованиями:
[docs/ux-contract-skill-matrix.md](docs/ux-contract-skill-matrix.md).

## Архитектура 0.2

`server.py` больше не содержит бизнес-логику. Он создаёт FastMCP, регистрирует
домены, применяет tool profile и запускает transport.

```text
src/alterios_mcp/
|- server.py           composition root
|- tools/              12 registration-модулей по доменам
|- scenarios/          orchestration, dry-run/apply/readback workflows
|- builders/           чистое построение payload и UI fragments
|- validators/         чистые проверки контрактов
|- client.py           HTTP client и route variants
|- tool_profiles.py    live/discovery/admin/full registry
|- write_plan.py       plan_id и проверка apply
`- runtime_info.py     fingerprint процесса и диагностика запуска
```

Правила развития:

1. Бизнес-операция создаётся в `scenarios/`.
2. Payload и validation выносятся в `builders/` и `validators/`.
3. `tools/<domain>.py` содержит только регистрацию public callable.
4. Tool name и schema являются совместимым публичным контрактом.
5. Изменение registry требует обновления golden snapshot.
6. После изменения обязательны pytest, replay smoke и public-tree scan.

Подробнее: [docs/architecture.md](docs/architecture.md).

## Агенты и private workboard

Рабочий delivery-контур использует три обязательные роли:

| Роль | Ответственность |
|---|---|
| `analyst` | Постановка, Mermaid-схема, модель данных и acceptance criteria |
| `implementer` | Реализация, dry-run/apply и артефакты |
| `verifier` | Независимые tests, readback, UI/render и риски |

PM ведёт private Gitea issue и `stage:*`, но не блокирует каждую техническую
операцию. Реальные URL, project IDs, названия материалов, HAR и screenshots не
публикуются в открытом репозитории.

Документы:

- [docs/development-cycle-and-agent-workflow.md](docs/development-cycle-and-agent-workflow.md);
- [docs/agents-and-skills.md](docs/agents-and-skills.md);
- [docs/gitea-private-workboard.md](docs/gitea-private-workboard.md);
- [docs/public-repository-data-policy.md](docs/public-repository-data-policy.md).

## Проверка разработки

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\alterios-replay-smoke.exe --json
git diff --check
.\.venv\Scripts\python.exe scripts\check_public_tree.py
```

Registry защищён golden snapshot: имена tools, схемы аргументов и состав
профилей не должны меняться случайно.

## Runtime и лишние процессы

Один активный MCP config обычно создаёт один логический сервер. На Windows
console launcher и дочерний `python.exe` могут отображаться как два связанных
процесса. Большое число независимых экземпляров обычно означает старые Codex
сессии, дублирующиеся MCP configs или не завершённые transports.

Используйте `alterios_runtime_info(include_processes=true)` для группировки по
instance fingerprint. После обновления:

1. Завершите старые Codex/MCP сессии.
2. Убедитесь, что в config одна запись `mcp_servers.alterios`.
3. Обновите release wheel или editable package.
4. Перезапустите Codex.
5. Проверьте runtime fingerprint и `alterios_replay_smoke`.

Подробнее: [docs/runtime-hygiene.md](docs/runtime-hygiene.md).

## Документация

- [Инструкция администратора](docs/administrator-guide.md)
- [Архитектура](docs/architecture.md)
- [Профили tools](docs/mcp-tool-profiles.md)
- [Контролируемая запись](docs/controlled-writes.md)
- [Расширенные сценарии](docs/expanded-user-scenarios.md)
- [Типы материалов и представлений](docs/material-types-and-view-types-research.md)
- [Формы и UX](docs/form-surface-ux-and-icons.md)
- [Иконки и действия](docs/alterios-icons-and-actions-catalog.md)
- [Скрипты](docs/script-runtime-catalog.md)
- [Stimulsoft](docs/stimulsoft-report-layout-and-analytics.md)
- [Дорожная карта](docs/roadmap.md)
- [История изменений](CHANGELOG.md)

## Граница публичного репозитория

В GitHub хранятся только переиспользуемый MCP-код, тесты, обезличенные правила,
skills, шаблоны и документация. Реальные бизнес-задачи, адреса систем, UUID,
названия материалов, пользователи, HAR, screenshots и результаты live-write
хранятся в private Gitea или локальном закрытом контуре.
