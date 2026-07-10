# Инструкция администратора alterios-mcp

Статус документа: эксплуатационная инструкция администратора.

Объект администрирования: MCP-сервер `alterios-mcp`, предназначенный для
инвентаризации, настройки и управляемой записи в Alterios/LIMS.

Стандартный ориентир: документ подготовлен как практическая эксплуатационная
инструкция для программного компонента. По структуре используется подход
ЕСПД/ГОСТ 19 к эксплуатационной документации, прежде всего ГОСТ 19.503
для настройки и сопровождения программного средства и ГОСТ 19.508 для
сопровождения. Формальное оформление с титульным листом, обозначением документа,
листом регистрации изменений и утверждающими подписями требует отдельного
шаблона заказчика.

## 1. Назначение

`alterios-mcp` предоставляет администраторам и инженерам безопасный программный
контур для работы с Alterios/LIMS через MCP-клиент.

Администратор использует MCP для следующих задач:

1. Подключение одного или нескольких экземпляров Alterios через профили.
2. Проверка доступности экземпляров и проектов.
3. Инвентаризация проектной базы Alterios.
4. Управляемая запись в проектную базу через типизированные инструменты.
5. Контроль write-gates, dry-run, readback и журналов проверки.
6. Установка и обновление локальных Codex skills для работы с Alterios.
7. Сопровождение документации и статуса разработки.

MCP не заменяет штатную систему прав Alterios. Все операции выполняются с
правами токена или учетной записи, указанных в конфигурации профиля.

## 2. Зона ответственности администратора

Администратор отвечает за:

- хранение токенов и приватных конфигураций вне репозитория;
- соответствие профиля реальному экземпляру Alterios;
- явное указание `project_id` для операций уровня проекта;
- проверку dry-run audit перед записью;
- включение write-gates только на безопасной целевой среде;
- запрет generic destructive/security операций без отдельного preflight;
- запуск регрессионных проверок перед обновлением рабочей копии;
- фиксацию проверенных этапов в `docs/project-status.md`;
- установку и актуализацию локальных skills, если они используются в Codex.

Администратор не должен:

- коммитить `.env`, токены, cookie, Authorization headers или реальные секреты;
- выполнять запись без dry-run и проверки целевого проекта;
- использовать generic REST write там, где есть типизированный инструмент;
- выполнять delete, users, roles, permissions или security operations без
  `alterios_write_safety_preflight` и отдельного подтвержденного сценария;
- редактировать чужие Alterios scripts без предварительного описания риска и
  плана проверки.

## 3. Состав поставки

Основные каталоги и файлы:

| Путь | Назначение |
|---|---|
| `src/alterios_mcp/` | Исходный код MCP-сервера, клиента, scanner-ов и validators. |
| `tests/` | Автоматические unit/smoke проверки без live-записи. |
| `scripts/artx_practice_metadata.py` | Воспроизводимый sandbox-сценарий для live-практики на тестовом проекте. |
| `scripts/install_repo_skills.py` | Установка repo-owned skills в локальный каталог Codex. |
| `skills/` | Набор проектных Alterios skills. |
| `docs/` | Документация, матрицы покрытия, статус, правила записи и playbook-и. |
| `.env.example` | Пример приватной конфигурации без реальных секретов. |
| `pyproject.toml` | Описание Python-пакета и console scripts. |
| `README.md` | Краткая пользовательская точка входа. |

Основные console scripts:

| Команда | Назначение |
|---|---|
| `alterios-mcp` | Запуск MCP-сервера. |
| `alterios-discover` | Проверка профилей и read-only discovery. |
| `alterios-profile-smoke` | Smoke-матрица профилей и default-проектов. |
| `alterios-deep-inventory` | Глубокая инвентаризация форм, скриптов, BPMN и иконок. |
| `alterios-form-surface-check` | Проверка формы на layout, источники данных, роли, стили и действия. |
| `alterios-stimulsoft-layout-check` | Проверка геометрии Stimulsoft template/report. |
| `alterios-static-scan` | Статический поиск известных routes и service-like names. |
| `alterios-ui-flow` | Анализ HAR/JSON сетевых flow из UI. |

## 4. Требования к среде

Минимальные требования:

- Windows с PowerShell;
- Python 3.11 или выше;
- Git;
- доступ к GitHub-репозиторию `alterios-mcp`;
- сетевой доступ до целевых экземпляров Alterios;
- токен или иной способ авторизации Alterios, совместимый с профилем;
- MCP-клиент, например Codex, если сервер используется не только через CLI.

Для разработки и проверки используется Python-пакет с dev-зависимостями:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## 5. Установка

Первичная установка:

```powershell
git clone https://github.com/SayAMSTASI/alterios-mcp.git
cd alterios-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

Проверка установки:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\alterios-discover.exe --profiles --json
```

Ожидаемый результат:

- тесты завершаются без ошибок;
- `alterios-discover` возвращает список профилей или сообщает, какие значения
  конфигурации отсутствуют;
- секреты в выводе не раскрываются.

## 6. Настройка профилей Alterios

### 6.1. Правило профилей

Один профиль соответствует одному экземпляру Alterios. Профиль не равен проекту.
Внутри одного экземпляра может быть много проектов, поэтому `project_id` для
project-level операций следует передавать явно.

Рекомендуется хранить приватную конфигурацию вне репозитория и подключать ее
через `ALTERIOS_DOTENV_PATH`.

Пример:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\path\to\private\alterios.env"
```

### 6.2. Пример приватного dotenv

```dotenv
ALTERIOS_PROFILE=primary
ALTERIOS_PROFILES=primary,secondary

ALTERIOS_PRIMARY_BASE_URL=https://alterios-primary.example.local
ALTERIOS_PRIMARY_API_TOKEN=put-token-here
ALTERIOS_PRIMARY_PROJECT_ID=put-optional-default-project-id-here
ALTERIOS_PRIMARY_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_PRIMARY_BODY_STYLE=manual_script
ALTERIOS_PRIMARY_AUTH_HEADER=x-api-key
ALTERIOS_PRIMARY_AUTH_SCHEME=
ALTERIOS_PRIMARY_TIMEOUT_SECONDS=20

ALTERIOS_SECONDARY_BASE_URL=https://alterios-secondary.example.local
ALTERIOS_SECONDARY_API_TOKEN=put-token-here
ALTERIOS_SECONDARY_PROJECT_ID=put-optional-default-project-id-here
ALTERIOS_SECONDARY_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_SECONDARY_BODY_STYLE=manual_script
ALTERIOS_SECONDARY_AUTH_HEADER=Authorization
ALTERIOS_SECONDARY_AUTH_SCHEME=Bearer
ALTERIOS_SECONDARY_TIMEOUT_SECONDS=20

ALTERIOS_MCP_ALLOW_WRITE=0
```

`ALTERIOS_<PROFILE>_PROJECT_ID` допускается использовать только как удобное
значение по умолчанию для повторяющейся read-only работы. Для записи `project_id`
должен передаваться в tool call явно.

### 6.3. Проверка профилей

Проверить локальную конфигурацию:

```powershell
.\.venv\Scripts\alterios-discover.exe --profiles --json
```

Проверить профили и доступность default-проектов:

```powershell
.\.venv\Scripts\alterios-profile-smoke.exe --json
```

Если профиль не проходит проверку, администратор должен проверить:

- наличие `ALTERIOS_DOTENV_PATH`;
- корректность имени профиля в `ALTERIOS_PROFILE` и `ALTERIOS_PROFILES`;
- `BASE_URL`;
- токен;
- тип авторизационного заголовка;
- доступность сети;
- наличие прав у токена;
- корректность default `PROJECT_ID`, если он задан.

## 7. Подключение MCP-сервера

### 7.1. Локальный запуск

```powershell
.\.venv\Scripts\alterios-mcp.exe
```

Если нужен fallback через Python:

```powershell
.\.venv\Scripts\python -m alterios_mcp.server
```

### 7.2. Подключение в Codex MCP config

Рекомендуемая форма:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\alterios-mcp.exe"
args = []
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\path\\to\\private\\alterios.env"
```

Fallback через Python:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\python.exe"
args = ["-m", "alterios_mcp.server"]
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\path\\to\\private\\alterios.env"
```

После изменения MCP config перезапустите MCP-клиент или сессию, чтобы перечитать
сервер и доступные инструменты.

## 8. Правила безопасной записи

Запись в Alterios выключена по умолчанию.

Для обычной записи должны быть выполнены все условия:

1. В tool call передан явный `profile`.
2. Для project-level операции передан явный `project_id`.
3. Tool call выполнен с `dry_run=false`.
4. В окружении MCP-процесса задано `ALTERIOS_MCP_ALLOW_WRITE=1`.
5. Целевой объект проверен через dry-run audit.
6. После записи выполнен readback или отдельная read-only проверка.

Для destructive/security операций дополнительно требуются:

1. Предварительный `alterios_write_safety_preflight`.
2. `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`.
3. Параметр `allow_destructive=true`.
4. Отдельно подтвержденный sandbox-сценарий.

К dangerous/security относятся:

- REST `DELETE`;
- операции под `/api/users`;
- операции под `/api/user-groups` и `/api/usergroups`;
- операции под `/api/roles`;
- операции под `/api/security`;
- операции под `/api/permissions`;
- service calls с destructive risk, например массовое удаление.

## 9. Регламент выполнения изменения

Используйте единый порядок для любого изменения проектной базы.

### 9.1. Подготовка

1. Определить целевой профиль и `project_id`.
2. Проверить профиль:

```powershell
.\.venv\Scripts\alterios-profile-smoke.exe --json
```

3. Убедиться, что выбран тестовый или согласованный целевой проект.
4. Подготовить параметры tool call.

### 9.2. Dry-run

1. Вызвать write-инструмент с dry-run режимом.
2. Проверить audit:
   - profile;
   - project_id;
   - route;
   - метод;
   - target object;
   - diff;
   - write gate status;
   - readback route или expected check.

Если audit не совпадает с ожидаемым объектом, запись выполнять нельзя.

### 9.3. Запись

Включить запись только для текущего MCP-процесса или контролируемой сессии:

```powershell
$env:ALTERIOS_MCP_ALLOW_WRITE = "1"
```

Повторить вызов с `dry_run=false`.

После завершения вернуть безопасное значение, если сессия продолжается:

```powershell
$env:ALTERIOS_MCP_ALLOW_WRITE = "0"
```

### 9.4. Readback

Проверить результат:

- через readback самого инструмента;
- через read-only tool;
- через `alterios-deep-inventory`, если изменение затрагивает формы, scripts,
  BPMN, reports или icons;
- через UI/HAR только когда изменение должно быть подтверждено пользовательским
  интерфейсом.

### 9.5. Фиксация результата

Если изменение является этапом проекта:

1. Обновить `docs/project-status.md`.
2. Указать commit, проверку, live evidence и риски.
3. Выполнить тесты и секрет-скан.
4. Сделать commit и push.

## 10. Основные административные сценарии

### 10.1. Инвентаризация проекта

Используется для понимания состава project base перед изменениями.

Рекомендуемые инструменты:

- MCP tools: `alterios_list_projects`, `alterios_list_objects`,
  `alterios_get_form`, `alterios_get_view`, `alterios_list_fields`,
  `alterios_report_full`;
- CLI: `alterios-deep-inventory`.

Результат инвентаризации должен отвечать на вопросы:

- какие content types и fields существуют;
- какие views и forms связаны с материалами;
- какие scripts запускаются из форм или BPMN;
- какие BPMN userTask открывают какие формы;
- какие reports используют Project Database source;
- какие iconId используются в действиях и группах.

### 10.2. Создание или изменение типа материалов

Предпочтительный путь:

1. `alterios_upsert_content_type`;
2. `alterios_upsert_field`;
3. `alterios_upsert_view`;
4. `alterios_upsert_view_entity`;
5. `alterios_upsert_view_field`;
6. `alterios_upsert_form`;
7. `alterios_upsert_group`;
8. `alterios_create_content` для тестовой записи.

Каждый шаг сначала выполняется в dry-run режиме.

### 10.3. Изменение формы

Перед изменением формы выполните read-only анализ:

- `alterios_get_form`;
- `alterios_analyze_form_surface`;
- при необходимости `alterios-deep-inventory`.

Проверить нужно:

- отсутствие пустых мест и логичность F-pattern;
- корректность `tabs`, `rows`, `cells`;
- источники данных `viewEntityId`, `openId`, `dataId`;
- роли, conditions, displaying, styles, params;
- icon-first действия;
- порядок действий: редактировать, просмотр, удалить;
- наличие меню строки через троеточие, если действие не должно занимать место
  отдельной кнопкой.

Для записи используйте:

- `alterios_upsert_form` для полной формы;
- `alterios_patch_form_tabs` для точечной замены вкладок;
- `alterios_patch_form_actions` для точечной замены action containers;
- `alterios_patch_form_cell_listeners` для точечной замены
  `tabs[tab].rows[row].cells[cell].emitting.listeners`.

### 10.4. Работа со скриптами и BPMN

Перед изменением:

1. Получить карту scripts/forms/BPMN.
2. Проверить, какие формы запускают scripts.
3. Проверить, какие BPMN tasks и listeners ссылаются на scripts.
4. Проверить, какие `userTask` открывают формы через `camunda:formKey`.

Для записи и проверки:

- `alterios_upsert_script`;
- `alterios_validate_script`;
- `alterios_execute_manual_script`;
- `alterios_upsert_bpmn_diagram`;
- `alterios_start_process`;
- `alterios_list_process_tasks`;
- `alterios_complete_task`;
- `alterios_validate_process_result`.

Запуск manual script и завершение task являются state-changing операциями и
должны выполняться только через controlled write workflow.

### 10.5. Работа с отчетами

Для отчетов на Project Database:

1. Проверить source view.
2. Проверить поля view и данные через `get-data` или `get-data-simplified`.
3. Подготовить Stimulsoft template.
4. Проверить layout через `alterios_validate_stimulsoft_layout` или
   `alterios-stimulsoft-layout-check`.
5. Сохранить отчет через `alterios_upsert_report` или обновить template через
   `alterios_patch_report_template`.
6. Проверить `alterios_validate_report_project_base`.

Для current-record отчетов в форме используйте контекст `dataId: [openId]`.
`contentId` сам по себе не является достаточной проверкой текущей строки.

Ограничение текущего этапа: статическая проверка Stimulsoft layout реализована,
но render/PDF/image comparison пока относится к backlog.

### 10.6. Users, user groups, roles, bulk selection

Для пользователей, групп пользователей и ролей используйте только typed security
tools:

- `alterios_list_users`, `alterios_get_user`, `alterios_upsert_user`,
  `alterios_delete_user`;
- `alterios_list_user_groups`, `alterios_get_user_group`,
  `alterios_upsert_user_group`, `alterios_delete_user_group`;
- `alterios_list_roles`, `alterios_get_role`, `alterios_upsert_role`,
  `alterios_delete_role`.

Эти tools считаются dangerous/security. Для live execution обязательны
`ALTERIOS_MCP_ALLOW_WRITE=1`, `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`,
`allow_destructive=true`, dry-run target review и readback. Для production
использовать их нельзя без отдельного sandbox/UI evidence и rollback-плана.

Для множественного выбора строк используйте
`alterios_bulk_update_selected_content_fields`, если действие не destructive:
передавайте `selected_content_ids`, `expected_count`, `expected_content_type_id`
и `field_values`. Массовое удаление или массовый запуск script требует
отдельного dangerous workflow.

Для публикации типа материала в другие проекты используйте
`alterios_plan_content_type_publish`. Это planner, а не запись. Native execution
разрешается добавлять только после UI/HAR evidence маршрута, payload shape и
readback правил по каждому target project.

### 10.7. Установка skills

Dry-run установки:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --json
```

Установка:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --execute --json
```

Принудительная замена установленной версии:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --replace --execute --json
```

После установки перезапустите Codex-сессию, чтобы skills появились в списке
доступных.

## 11. Контроль качества перед commit/push

Перед commit:

```powershell
.\.venv\Scripts\python -m pytest
git diff --check
```

Проверить README и документацию на случайные секреты:

```powershell
rg -n "(Bearer\s+[A-Za-z0-9._-]{20,}|\bsk-[A-Za-z0-9]{20,}|ALTERIOS_[A-Z0-9_]*=.*[A-Za-z0-9]{30,}|password\s*=\s*[^<\s].{8,})" README.md docs
```

Код возврата `1` у `rg` без вывода означает, что совпадений не найдено.

Перед push:

```powershell
git status --short
git log --oneline -3
git push origin main
```

Рабочее дерево должно быть чистым после push.

## 12. Журналирование и доказательства

Для каждого значимого этапа фиксируйте:

- что изменено;
- какой профиль и проект использовались;
- выполнялась ли live-запись;
- какой dry-run был просмотрен;
- какой readback подтвердил результат;
- какие тесты запускались;
- были ли секреты в измененных файлах;
- какие риски остались.

Основной файл статуса: `docs/project-status.md`.

Для live evidence используйте sanitized artifacts: без токенов, cookie, реальных
секретов, лишних URL и персональных данных.

## 13. Диагностика

### 13.1. MCP-сервер не запускается

Проверьте:

- активирована ли виртуальная среда или указан абсолютный путь к `.venv`;
- установлен ли пакет через `pip install -e ".[dev]"`;
- корректен ли путь в MCP config;
- не истек ли `startup_timeout_sec`;
- нет ли ошибки импорта в `python -m alterios_mcp.server`.

Команда проверки:

```powershell
.\.venv\Scripts\python -m alterios_mcp.server
```

### 13.2. Профиль не найден

Проверьте:

- `ALTERIOS_DOTENV_PATH`;
- `ALTERIOS_PROFILE`;
- `ALTERIOS_PROFILES`;
- имя prefix-переменных, например `ALTERIOS_PRIMARY_BASE_URL`.

Команда:

```powershell
.\.venv\Scripts\alterios-discover.exe --profiles --json
```

### 13.3. Read-only route возвращает 404

Возможные причины:

- указан project_id от другого экземпляра;
- маршрут зависит от версии Alterios;
- объект был удален или находится в другом проекте;
- профиль указывает не на тот base URL.

Сначала проверьте `alterios_config`, затем список проектов и только потом
повторяйте project-level read.

### 13.4. Запись не выполняется

Проверьте:

- `dry_run=false`;
- `ALTERIOS_MCP_ALLOW_WRITE=1`;
- явный `profile`;
- явный `project_id`;
- target object в audit;
- отсутствие dangerous route без дополнительных gate-флагов.

Для dangerous route дополнительно:

```powershell
$env:ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE = "1"
```

И в tool call должен быть `allow_destructive=true`.

### 13.5. Отчет в форме не отображается

Проверить нужно отдельно:

- report full readback;
- source view и view data;
- `params.openId`;
- `dataId: [openId]` для current-record контекста;
- наличие network ошибок в UI;
- Stimulsoft template layout.

Известное ограничение: embedded report viewer в in-app browser ранее показывал
пустой `viewer_*` container даже при API-readback. Не считать visual render
подтвержденным без отдельной UI/render проверки.

### 13.6. Кириллица выглядит некорректно в PowerShell

Файлы репозитория хранятся в UTF-8. Некорректный вывод в консоли не означает,
что файл поврежден.

Для проверки используйте Python с явным UTF-8:

```powershell
@'
from pathlib import Path
text = Path("docs/administrator-guide.md").read_text(encoding="utf-8")
print(text[:200])
'@ | .\.venv\Scripts\python -
```

## 14. Обновление MCP

Порядок обновления рабочей копии:

1. Проверить чистоту дерева:

```powershell
git status --short
```

2. Получить изменения:

```powershell
git pull --ff-only
```

3. Обновить editable install при необходимости:

```powershell
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

4. Запустить проверки:

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\alterios-discover.exe --profiles --json
```

5. Если обновлялись skills:

```powershell
.\.venv\Scripts\python scripts\install_repo_skills.py --replace --execute --json
```

6. Перезапустить MCP-клиент.

## 15. Резервное копирование и восстановление

Репозиторий не хранит production-секреты и не является резервной копией Alterios.

Администратор должен отдельно обеспечить:

- резервное копирование приватного dotenv-файла;
- хранение токенов в защищенном хранилище;
- возможность отзыва скомпрометированного токена;
- резервную копию Alterios или проектной базы средствами владельца Alterios;
- сохранение sanitized evidence в репозитории только без секретов.

Для восстановления MCP-доступа достаточно:

1. Клонировать репозиторий.
2. Создать `.venv`.
3. Установить пакет.
4. Подключить приватный dotenv через `ALTERIOS_DOTENV_PATH`.
5. Запустить profile smoke.
6. Перезапустить MCP-клиент.

## 16. Текущее состояние разработки

На текущем этапе основной функциональный контур разработки закрывается для
эксплуатации:

- есть 66 MCP-инструментов;
- есть 31 write-like инструмент;
- реализованы профили нескольких экземпляров Alterios;
- реализованы read-only inventory и deep inventory;
- реализованы controlled write gates;
- реализованы typed write tools для metadata/data, files, forms/views,
  scripts/BPMN/tasks и reports;
- реализованы typed security tools для users/user-groups/roles/delete с
  dangerous gate и no-network тестами;
- реализованы typed form listener patch и bulk selected-content update;
- реализован planner для native content-type publish/transfer без live записи;
- реализованы repo-owned skills и installer;
- создан Documentation Scribe / Писарь;
- README переведен в пользовательскую точку входа;
- настоящая инструкция закрывает административный контур.

Оставшиеся работы не должны блокировать эксплуатацию текущего MCP:

- live execution destructive/security tools разрешать только после UI/HAR/API
  evidence, rollback-плана и sandbox readback;
- executing native content-type publish tool добавлять только после UI/HAR
  route и payload evidence;
- Stimulsoft render/PDF/image comparison остается расширением validator-а;
- release packaging и changelog process остаются отдельным release-этапом.

## 17. Контрольный чек-лист администратора

Перед использованием:

- [ ] Репозиторий установлен.
- [ ] `.venv` создана.
- [ ] Пакет установлен через `pip install -e ".[dev]"`.
- [ ] `ALTERIOS_DOTENV_PATH` указывает на приватный dotenv вне репозитория.
- [ ] `alterios-discover --profiles --json` проходит.
- [ ] `alterios-profile-smoke --json` проходит для нужных профилей.
- [ ] MCP config указывает на `alterios-mcp.exe`.
- [ ] MCP-клиент перезапущен.
- [ ] Write-gate выключен по умолчанию.

Перед записью:

- [ ] Передан явный `profile`.
- [ ] Передан явный `project_id`.
- [ ] Dry-run audit проверен.
- [ ] Target object совпадает с ожидаемым.
- [ ] Для записи включен `ALTERIOS_MCP_ALLOW_WRITE=1`.
- [ ] Для dangerous/security route выполнен preflight.
- [ ] Для dangerous/security route включен отдельный dangerous gate.
- [ ] После записи выполнен readback.
- [ ] Результат зафиксирован в статусе, если это этап проекта.

Перед завершением работы:

- [ ] `ALTERIOS_MCP_ALLOW_WRITE` возвращен в `0` или сессия закрыта.
- [ ] Нет незакоммиченных рабочих изменений.
- [ ] Тесты пройдены.
- [ ] Секрет-скан не нашел совпадений.
- [ ] Изменения запушены, если они должны попасть в общий репозиторий.
